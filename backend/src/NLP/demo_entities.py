"""Quick demo runner for entity extraction + KG linking.

Usage:
    python src/backend/NLP/demo_entities.py "ingredientes da francesinha"
"""

import os
import sys

# Support both package and direct script execution
try:
    from .entity_extraction import extract_and_link 
except Exception:
    sys.path.append(os.path.dirname(__file__))
    from entity_extraction import extract_and_link  


def main():
    if len(sys.argv) < 2:
        print("Provide a query string, e.g.: python demo_entities.py 'ingredientes da francesinha'")
        sys.exit(1)

    query = sys.argv[1]
    base_dir = os.path.dirname(__file__)
    default_a = os.path.normpath(os.path.join(base_dir, "../../data/curated/recipes_graph_cleaned.ttl"))
    default_b = os.path.normpath(os.path.join(base_dir, "../../data/curated/example.ttl"))
    ttl_path = default_a if os.path.exists(default_a) else default_b

    result = extract_and_link(query, ttl_path, lang_priority="pt")
    print("Query:", query)
    print("Linked slots:")
    print(result)


if __name__ == "__main__":
    main()
