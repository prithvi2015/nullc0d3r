# -*- coding: utf-8 -*-
import json
import requests
import pandas as pd
import argparse
import os

def load_json(file_path_or_url):
    """ Load JSON from a file or URL """
    if file_path_or_url.startswith("http"):
        try:
            response = requests.get(file_path_or_url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print("❌ Error: Failed to fetch JSON from URL: {}".format(e))
            return None
    else:
        if not os.path.exists(file_path_or_url):
            print("❌ Error: File not found at {}".format(file_path_or_url))
            return None
        try:
            with open(file_path_or_url, "r") as file:
                return json.load(file)
        except Exception as e:
            print("❌ Error: Unable to read the JSON file: {}".format(e))
            return None

def detect_file_type(json_data):
    """ Detect whether the file is OpenAPI 3.x, Swagger 2.0, or a Postman Collection """
    if "openapi" in json_data:
        return "openapi3"
    elif "swagger" in json_data:
        return "swagger2"
    elif "info" in json_data and "item" in json_data:
        return "postman"
    return None

# ----------- OpenAPI & Swagger Analysis ----------- #

def count_api_endpoints(openapi_data):
    """ Count total API endpoints """
    return len(openapi_data.get("paths", {})) if openapi_data else 0

def count_http_methods(openapi_data):
    """ Count occurrences of HTTP methods """
    method_counts = {}
    if openapi_data:
        for methods in openapi_data.get("paths", {}).values():
            for method in methods.keys():
                method_counts[method] = method_counts.get(method, 0) + 1
    return method_counts

def count_parameters(openapi_data, version):
    """ Count query/path/header parameters and body parameters separately """
    total_parameters = 0
    total_body_parameters = 0
    unique_parameters = set()

    if openapi_data:
        for methods in openapi_data.get("paths", {}).values():
            for details in methods.values():
                if "parameters" in details:
                    for param in details["parameters"]:
                        if isinstance(param, dict) and "name" in param:
                            unique_parameters.add(param["name"])
                        if param.get("in") == "body" and version == "swagger2":
                            total_body_parameters += 1
                    total_parameters += len(details["parameters"])

                if version == "openapi3" and "requestBody" in details:
                    total_body_parameters += 1
    
    return total_parameters, total_body_parameters, unique_parameters

def extract_schema_parameters(components, schema_name, visited=None):
    """ Recursively extract all properties from a schema and nested references """
    if visited is None:
        visited = set()
    if schema_name in visited or schema_name not in components:
        return set()

    visited.add(schema_name)
    schema = components[schema_name]
    params = set()

    if "properties" in schema:
        params.update(schema["properties"].keys())
        for prop_details in schema["properties"].values():
            if "$ref" in prop_details:
                ref_schema = prop_details["$ref"].split("/")[-1]
                params.update(extract_schema_parameters(components, ref_schema, visited))
    
    return params

def count_deep_schema_parameters(openapi_data, version):
    """ Extract deep schema parameters from OpenAPI components """
    components = openapi_data.get("components", {}).get("schemas", {}) if version == "openapi3" else openapi_data.get("definitions", {}) if version == "swagger2" else {}
    deep_parameters = set()

    if openapi_data:
        for methods in openapi_data.get("paths", {}).values():
            for details in methods.values():
                if version == "openapi3" and "requestBody" in details:
                    content = details["requestBody"].get("content", {})
                    for media_details in content.values():
                        if "schema" in media_details and "$ref" in media_details["schema"]:
                            ref_schema_name = media_details["schema"]["$ref"].split("/")[-1]
                            deep_parameters.update(extract_schema_parameters(components, ref_schema_name))
                
                if version == "swagger2" and "parameters" in details:
                    for param in details["parameters"]:
                        if "schema" in param and "$ref" in param["schema"]:
                            ref_schema_name = param["schema"]["$ref"].split("/")[-1]
                            deep_parameters.update(extract_schema_parameters(components, ref_schema_name))
    
    return deep_parameters

# ----------- Postman Collection Analysis ----------- #

def extract_query_params(url):
    """ Extract query parameters from Postman Collection requests """
    if "query" in url:
        return {param["key"] for param in url["query"]}
    return set()

def extract_body_params(body):
    """ Extract body parameters from Postman Collection requests """
    if body and body.get("mode") == "raw" and body.get("raw"):
        try:
            parsed_body = json.loads(body["raw"])
            return set(parsed_body.keys()) if isinstance(parsed_body, dict) else set()
        except ValueError:  # Replacing json.JSONDecodeError for compatibility
            return set()  # Ignore non-JSON body
    return set()

def analyze_openapi(file_path_or_url, version):
    """ Perform full OpenAPI analysis on a given file or URL """
    openapi_data = load_json(file_path_or_url)
    if not openapi_data:
        return {"Error": "Failed to load OpenAPI data. Check the file path or URL."}

    total_endpoints = count_api_endpoints(openapi_data)
    method_counts = count_http_methods(openapi_data)
    total_parameters, total_body_parameters, unique_parameters = count_parameters(openapi_data, version)
    deep_parameters = count_deep_schema_parameters(openapi_data, version)
    all_unique_parameters = unique_parameters.union(deep_parameters)

    analysis_results = {
        "OpenAPI Version": version,
        "Total API Endpoints": total_endpoints,
        "HTTP Methods Count": method_counts,
        "Total Parameters (including body parameters)": total_parameters + total_body_parameters,
        "Total Body Parameters": total_body_parameters,
        "Deep Schema Parameters": len(deep_parameters),
        "Unique Parameters (Including Deep Analysis)": len(all_unique_parameters),
        "List of Unique Parameters": list(all_unique_parameters)
    }
    
    return analysis_results


def analyze_postman_collection(postman_data):
    """ Perform analysis on a Postman Collection """
    total_requests = 0
    http_methods_count = {}
    unique_parameters = set()
    total_query_parameters = 0
    total_body_parameters = 0

    for item in postman_data.get("item", []):
        if "item" in item:  # Folder containing multiple requests
            for request in item["item"]:
                total_requests += 1
                method = request["request"]["method"]

                # Count HTTP methods
                http_methods_count[method] = http_methods_count.get(method, 0) + 1

                # Extract query parameters
                unique_parameters.update(extract_query_params(request["request"]["url"]))
                total_query_parameters += len(extract_query_params(request["request"]["url"]))

                # Extract body parameters
                unique_parameters.update(extract_body_params(request["request"]["body"]))
                total_body_parameters += len(extract_body_params(request["request"]["body"]))

    return {
        "Total Requests": total_requests,
        "HTTP Methods Count": http_methods_count,
        "Total Query Parameters": total_query_parameters,
        "Total Body Parameters": total_body_parameters,
        "Unique Parameters (Including Query & Body)": len(unique_parameters),
        "List of Unique Parameters": list(unique_parameters),
    }

# ----------- Main Analysis Function ----------- #

def analyze_json(file_path_or_url):
    """ Perform full analysis on OpenAPI or Postman Collection """
    json_data = load_json(file_path_or_url)
    if not json_data:
        return {"Error": "Failed to load JSON data. Check the file path or URL."}

    file_type = detect_file_type(json_data)
    
    if file_type in ["openapi3", "swagger2"]:
        return analyze_openapi(file_path_or_url, file_type)
    elif file_type == "postman":
        return analyze_postman_collection(json_data)
    else:
        return {"Error": "Unknown API specification format."}

def main():
    """ Command-line interface for analyzing OpenAPI or Postman JSON files """
    parser = argparse.ArgumentParser(description="Analyze an OpenAPI JSON or Postman Collection file.")
    parser.add_argument("input", type=str, help="Path to the JSON file or URL")
    args = parser.parse_args()
    
    analysis_results = analyze_json(args.input)
    
    print("\n📊 API Analysis Results:\n")
    for i, (key, value) in enumerate(analysis_results.items(), start=1):
        print("{}. {}: {}".format(i, key, value))


if __name__ == "__main__":
    main()
