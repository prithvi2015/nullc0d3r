# -*- coding: utf-8 -*-
import json
import requests
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

def analyze_openapi(file_path_or_url, version):
    """ Perform full OpenAPI analysis on a given file or URL """
    openapi_data = load_json(file_path_or_url)
    if not openapi_data:
        return {"Error": "Failed to load OpenAPI data. Check the file path or URL."}

    total_endpoints = len(openapi_data.get("paths", {}))
    method_counts = {}

    unique_parameters = set()
    total_parameters = 0
    total_body_parameters = 0
    deep_parameters = set()

    for path, methods in openapi_data.get("paths", {}).items():
        for method, details in methods.items():
            method_counts[method] = method_counts.get(method, 0) + 1

            # Extract parameters
            if "parameters" in details:
                for param in details["parameters"]:
                    if "name" in param:
                        unique_parameters.add(param["name"])
                total_parameters += len(details["parameters"])

            # Extract body parameters
            if "requestBody" in details:
                content = details["requestBody"].get("content", {})
                for media_type, media_details in content.items():
                    if "schema" in media_details:
                        schema = media_details["schema"]
                        if "$ref" in schema:
                            deep_parameters.add(schema["$ref"].split("/")[-1])
                        total_body_parameters += 1

    analysis_results = {
        "OpenAPI Version": version,
        "Total API Endpoints": total_endpoints,
        "HTTP Methods Count": method_counts,
        "Total Parameters (including body parameters)": total_parameters + total_body_parameters,
        "Total Body Parameters": total_body_parameters,
        "Deep Schema Parameters": len(deep_parameters),
        "Unique Parameters (Including Deep Analysis)": len(unique_parameters.union(deep_parameters)),
        "List of Unique Parameters": list(unique_parameters.union(deep_parameters)),
    }

    return analysis_results

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
        except ValueError:
            return set()  # Ignore non-JSON body
    return set()

def analyze_postman_collection(postman_data):
    """ Perform analysis on a Postman Collection, including nested folders """
    total_requests = 0
    http_methods_count = {}
    unique_parameters = set()
    total_query_parameters = 0
    total_body_parameters = 0

    def process_requests(items, total_requests, total_query_parameters, total_body_parameters):
        """ Recursively process requests, handling folders """
        for item in items:
            if "item" in item:  # If item is a folder, recursively process it
                total_requests, total_query_parameters, total_body_parameters = process_requests(
                    item["item"], total_requests, total_query_parameters, total_body_parameters
                )
                continue

            if "request" not in item:  # Skip invalid items
                continue

            total_requests += 1
            method = item["request"]["method"]

            # Count HTTP methods
            http_methods_count[method] = http_methods_count.get(method, 0) + 1

            # Extract query parameters
            unique_parameters.update(extract_query_params(item["request"]["url"]))
            total_query_parameters += len(extract_query_params(item["request"]["url"]))

            # Extract body parameters
            if "body" in item["request"]:
                unique_parameters.update(extract_body_params(item["request"]["body"]))
                total_body_parameters += len(extract_body_params(item["request"]["body"]))

        return total_requests, total_query_parameters, total_body_parameters

    # Start processing requests, handling folders
    total_requests, total_query_parameters, total_body_parameters = process_requests(
        postman_data.get("item", []), total_requests, total_query_parameters, total_body_parameters
    )

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
