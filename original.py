# -*- coding: utf-8 -*-
import json
import requests
import argparse
import os
import math

# Utility to load JSON data
def load_json(file_path_or_url):
    if file_path_or_url.startswith("http"):
        response = requests.get(file_path_or_url)
        response.raise_for_status()
        return response.json()
    elif os.path.exists(file_path_or_url):
        with open(file_path_or_url, "r") as f:
            return json.load(f)
    else:
        print(u"❌ Error: Path not found - {}".format(file_path_or_url))
        return None

# Detect the type of API schema
def detect_file_type(json_data):
    if "openapi" in json_data:
        return "openapi3"
    elif "swagger" in json_data:
        return "swagger2"
    elif "info" in json_data and "item" in json_data:
        return "postman"
    elif json_data.get("data", {}).get("__schema"):
        return "graphql"
    return None

# Resolve JSON reference deeply
def resolve_ref(ref, full_schema):
    parts = ref.strip('#/').split('/')
    resolved = full_schema
    for part in parts:
        resolved = resolved.get(part, {})
    return resolved

# Recursive extraction of schema properties
def extract_schema_properties(schema, full_schema, unique_params, seen_refs=None):
    if seen_refs is None:
        seen_refs = set()

    if schema is None or not isinstance(schema, dict):
        return

    if "$ref" in schema:
        ref_id = schema["$ref"]
        if ref_id in seen_refs:
            return
        seen_refs.add(ref_id)
        ref_schema = resolve_ref(ref_id, full_schema)
        extract_schema_properties(ref_schema, full_schema, unique_params, seen_refs)

    if "properties" in schema:
        for prop, prop_spec in schema["properties"].items():
            unique_params.add(prop)
            extract_schema_properties(prop_spec, full_schema, unique_params, seen_refs)

    for composite in ["allOf", "anyOf", "oneOf"]:
        if composite in schema:
            for subschema in schema[composite]:
                extract_schema_properties(subschema, full_schema, unique_params, seen_refs)

# Analysis for OpenAPI and Swagger schemas
def analyze_openapi(json_data, version):
    endpoints = len(json_data.get("paths", {}))
    total_requests = 0
    methods = {}
    unique_params = set()

    for path, path_item in json_data.get("paths", {}).items():
        for method, spec in path_item.items():
            method_upper = method.upper()
            methods[method_upper] = methods.get(method_upper, 0) + 1
            total_requests += 1  # Increment request count

            for param in spec.get("parameters", []):
                if "$ref" in param:
                    resolved_param = resolve_ref(param["$ref"], json_data)
                    if "name" in resolved_param:
                        unique_params.add(resolved_param["name"])
                elif "name" in param:
                    unique_params.add(param["name"])

            if "requestBody" in spec:
                content = spec["requestBody"].get("content", {})
                for media_type in content.values():
                    schema = media_type.get("schema", {})
                    extract_schema_properties(schema, json_data, unique_params)

            testing_days = max(1, (total_requests + 3) // 4)

    return {
        "API Version": version,
        "Total Requests": total_requests,
        "Testing Days": testing_days,
        "Total Endpoints": endpoints,
        "HTTP Methods": methods,
        "Unique Parameters (Deep Analysis)": len(unique_params)
    }

# Analysis for Postman collections
def analyze_postman_collection(postman_data):
    def process_requests(items, counts):
        for item in items:
            if "item" in item:
                process_requests(item["item"], counts)
                continue
            if "request" not in item:
                continue
            counts["Total Requests"] += 1
            method = item["request"].get("method", "UNKNOWN")
            counts["HTTP Methods Count"][method] = counts["HTTP Methods Count"].get(method, 0) + 1

            if "url" in item["request"] and "query" in item["request"]["url"]:
                counts["Unique Parameters"].update(
                    param["key"] for param in item["request"]["url"]["query"]
                )
                counts["Total Query Parameters"] += len(item["request"]["url"]["query"])

            if "body" in item["request"]:
                counts["Total Body Parameters"] += 1

    counts = {
        "Total Requests": 0,
        "HTTP Methods Count": {},
        "Total Query Parameters": 0,
        "Total Body Parameters": 0,
        "Unique Parameters": set()
    }

    process_requests(postman_data.get("item", []), counts)

    counts["Unique Parameters"] = len(counts["Unique Parameters"])
    counts["Testing Days"] = max(1, (counts["Total Requests"] + 3) // 4)
    return counts

# Analysis for GraphQL introspection schema
def analyze_graphql(schema_json):
    schema_info = schema_json.get("data", {}).get("__schema", {})
    types = schema_info.get("types", [])

    query_type_name = schema_info.get("queryType", {}).get("name") if schema_info.get("queryType") else None
    mutation_type_name = schema_info.get("mutationType", {}).get("name") if schema_info.get("mutationType") else None
    subscription_type_name = schema_info.get("subscriptionType", {}).get("name") if schema_info.get("subscriptionType") else None

    query_count = mutation_count = subscription_count = 0

    for t in types:
        type_name = t.get("name", "")
        fields = t.get("fields", [])

        if type_name == query_type_name:
            query_count += len(fields) if fields else 0
        elif type_name == mutation_type_name:
            mutation_count += len(fields) if fields else 0
        elif type_name == subscription_type_name:
            subscription_count += len(fields) if fields else 0

    total_types = len(types)
    total_fields = sum(len(t.get("fields") or []) for t in types)
    total_requests = query_count + mutation_count + subscription_count
    testing_days = max(1, (total_requests + 3) // 4)

    return {
        "Queries": query_count,
        "Mutations": mutation_count,
        "Subscriptions": subscription_count,
        "Total Types": total_types,
        "Total Fields": total_fields,
        "Total Requests": total_requests,
        "Testing Days": testing_days
    }




# GraphQL introspection via endpoint
def graphql_introspection_check(endpoint):
    introspection_query = '{"query":"query IntrospectionQuery { __schema { queryType { name } mutationType { name } subscriptionType { name } types { name fields { name args { name } } } } }"}'
    headers = {'Content-Type': 'application/json'}

    print("Fetching GraphQL schema from {}".format(endpoint))
    response = requests.post(endpoint, data=introspection_query, headers=headers)

    if response.status_code == 200:
        schema_json = response.json()
        if schema_json.get("data", {}).get("__schema"):
            print("✅ Introspection enabled via POST")
            return analyze_graphql(schema_json)
        else:
            print("❌ Introspection query succeeded but no schema found.")
    else:
        print("❌ GraphQL introspection failed with status code: {}".format(response.status_code))

    return {"Error": "GraphQL introspection not enabled via POST"}

# Main function explicitly handling GraphQL endpoints and files
def main(input_file):
    if input_file.startswith("http") and "graphql" in input_file.lower():
        results = graphql_introspection_check(input_file)
    else:
        json_data = load_json(input_file)
        if not json_data:
            return

        file_type = detect_file_type(json_data)

        if file_type in ["openapi3", "swagger2"]:
            results = analyze_openapi(json_data, file_type)
        elif file_type == "postman":
            results = analyze_postman_collection(json_data)
        elif file_type == "graphql":
            results = analyze_graphql(json_data)
        else:
            results = {"Error": "Unknown schema type"}

    print("\nAPI Analysis Results:\n")
    for key, value in results.items():
        print("{}: {}".format(key, value))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="API Schema Analyzer")
    parser.add_argument("input", type=str, help="Path to the API schema file (JSON) or GraphQL endpoint URL")
    args = parser.parse_args()

    main(args.input)

