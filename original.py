# -*- coding: utf-8 -*-
import json
import requests
import pandas as pd
import argparse
import os

def load_openapi(file_path_or_url):
    """ Load OpenAPI JSON from a file or URL """
    if file_path_or_url.startswith("http"):
        try:
            response = requests.get(file_path_or_url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print("❌ Error: Failed to fetch OpenAPI JSON from URL: {}".format(e))
            return None
    else:
        if not os.path.exists(file_path_or_url):
            print("❌ Error: File not found at {}".format(file_path_or_url))
            return None
        try:
            with open(file_path_or_url, "r") as file:
                return json.load(file)
        except Exception as e:
            print("❌ Error: Unable to read the OpenAPI file: {}".format(e))
            return None

def count_api_endpoints(openapi_data):
    """ Count total API endpoints """
    return len(openapi_data.get("paths", {})) if openapi_data else 0

def count_http_methods(openapi_data):
    """ Count occurrences of HTTP methods (GET, POST, etc.) """
    method_counts = {}
    if openapi_data:
        for methods in openapi_data.get("paths", {}).values():
            for method in methods.keys():
                method_counts[method] = method_counts.get(method, 0) + 1
    return method_counts

def count_parameters(openapi_data):
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
                    total_parameters += len(details["parameters"])
                
                if "requestBody" in details:
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

def count_deep_schema_parameters(openapi_data):
    """ Extract deep schema parameters from OpenAPI components """
    components = openapi_data.get("components", {}).get("schemas", {}) if openapi_data else {}
    deep_parameters = set()

    if openapi_data:
        for methods in openapi_data.get("paths", {}).values():
            for details in methods.values():
                if "requestBody" in details:
                    content = details["requestBody"].get("content", {})
                    for media_details in content.values():
                        if "schema" in media_details:
                            schema = media_details["schema"]
                            if "$ref" in schema:
                                ref_schema_name = schema["$ref"].split("/")[-1]
                                deep_parameters.update(extract_schema_parameters(components, ref_schema_name))
    
    return deep_parameters

def analyze_openapi(file_path_or_url):
    """ Perform full OpenAPI analysis on a given file or URL """
    openapi_data = load_openapi(file_path_or_url)
    if not openapi_data:
        return {"Error": "Failed to load OpenAPI data. Check the file path or URL."}
    
    total_endpoints = count_api_endpoints(openapi_data)
    method_counts = count_http_methods(openapi_data)
    total_parameters, total_body_parameters, unique_parameters = count_parameters(openapi_data)
    deep_parameters = count_deep_schema_parameters(openapi_data)
    all_unique_parameters = unique_parameters.union(deep_parameters)

    analysis_results = {
        "HTTP Methods Count": method_counts,
        "Total API Endpoints": total_endpoints,
        "Total Parameters (including body parameters)": total_parameters + total_body_parameters,
        "Total Body Parameters": total_body_parameters,
        "Deep Schema Parameters": len(deep_parameters),
        "Unique Parameters (Including Deep Analysis)": len(all_unique_parameters),
        "List of Unique Parameters": list(all_unique_parameters)
    }
    
    return analysis_results

def display_results(analysis_results):
    """ Display the results in a numbered list format """
    print("\n📊 OpenAPI Analysis Results:\n")
    
    for i, (key, value) in enumerate(analysis_results.items(), start=1):
        if isinstance(value, list):
            print("{}. {}: [{} items]".format(i, key, len(value)))
        else:
            print("{}. {}: {}".format(i, key, value))

def main():
    """ Command-line interface for analyzing OpenAPI files """
    parser = argparse.ArgumentParser(description="Analyze an OpenAPI JSON file or URL.")
    parser.add_argument("input", type=str, help="Path to the OpenAPI JSON file or URL")
    parser.add_argument("--export", type=str, choices=["csv", "json"], help="Export results as CSV or JSON")
    args = parser.parse_args()
    
    analysis_results = analyze_openapi(args.input)
    
    # Display results in a numbered format
    display_results(analysis_results)

    # Export results if requested
    if args.export:
        output_file = "openapi_analysis." + args.export
        df_analysis_results = pd.DataFrame(list(analysis_results.items()), columns=["Metric", "Value"])
        
        if args.export == "csv":
            df_analysis_results.to_csv(output_file, index=False)
        elif args.export == "json":
            df_analysis_results.to_json(output_file, orient="records", indent=4)
        
        print("\n✅ Results exported as {}\n".format(output_file))

if __name__ == "__main__":
    main()
