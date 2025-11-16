# sparql_queries.py
from rdflib import Graph, Namespace, RDF, RDFS, URIRef

EX = Namespace("http://example.org/recipes#")

def _esc(s: str) -> str:
    return s.replace('"', '\\"')

def query_list_by_ingredient(graph: Graph, ingredient_name: str):
    """
    Retorna receitas que contenham o ingrediente, com recipe_name, tags, n_steps, nutrition.
    Top-k receitas.
    """
    needle = _esc(ingredient_name)
    q = f"""
    SELECT ?recipe ?label ?n_steps ?nutrition ?tagLabel WHERE {{
        ?recipe rdf:type ex:Recipe .
        ?recipe rdfs:label ?label .
        ?recipe ex:hasIngredient ?ing .
        ?ing rdfs:label ?ingLabel .
        FILTER(CONTAINS(LCASE(STR(?ingLabel)), LCASE("{needle}")))
        ?recipe ex:n_steps ?n_steps .
        ?recipe ex:hasNutrition ?nutrition .
        ?recipe ex:hasTag ?tag .
        ?tag rdfs:label ?tagLabel .
    }} LIMIT 2
    """
    results = []
    for row in graph.query(q, initNs={"ex": EX, "rdf": RDF, "rdfs": RDFS}):
        results.append({
            "recipe_uri": str(row.recipe),
            "recipe_name": str(row.label),
            "n_steps": int(row.n_steps),
            "nutrition": str(row.nutrition),
            "tag": str(row.tagLabel)
        })
    return results


def query_list_by_tag(graph: Graph, tag_name: str):
    """
    Retorna uma receita que tenha a tag, com recipe_name, n_steps, nutrition.
    Top 1.
    """
    needle = _esc(tag_name)
    q = f"""
    SELECT ?recipe ?label ?n_steps ?nutrition WHERE {{
        ?recipe rdf:type ex:Recipe .
        ?recipe rdfs:label ?label .
        ?recipe ex:hasTag ?t .
        ?t rdfs:label ?tagLabel .
        FILTER(CONTAINS(LCASE(STR(?tagLabel)), LCASE("{needle}")))
        ?recipe ex:n_steps ?n_steps .
        ?recipe ex:hasNutrition ?nutrition .
    }} LIMIT 1
    """
    for row in graph.query(q, initNs={"ex": EX, "rdf": RDF, "rdfs": RDFS}):
        return {
            "recipe_uri": str(row.recipe),
            "recipe_name": str(row.label),
            "n_steps": int(row.n_steps),
            "nutrition": str(row.nutrition),
        }
    return None


def query_find_recipe(graph: Graph, recipe_name: str):
    """
    Retorna todos os dados de uma receita (uma) pelo nome.
    """
    needle = _esc(recipe_name)
    q = f"""
    SELECT ?recipe ?label ?n_steps ?nutrition ?id ?minutes ?n_ingredients ?origin WHERE {{
        ?recipe rdf:type ex:Recipe .
        ?recipe rdfs:label ?label .
        FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{needle}")))
        ?recipe ex:n_steps ?n_steps .
        ?recipe ex:hasNutrition ?nutrition .
        ?recipe ex:id ?id .
        ?recipe ex:minutes ?minutes .
        ?recipe ex:n_ingredients ?n_ingredients .
        ?recipe ex:origin ?origin .
    }} LIMIT 1
    """
    for row in graph.query(q, initNs={"ex": EX, "rdf": RDF, "rdfs": RDFS}):
        return {
            "recipe_uri": str(row.recipe),
            "recipe_name": str(row.label),
            "n_steps": int(row.n_steps),
            "nutrition": str(row.nutrition),
            "id": int(row.id),
            "minutes": int(row.minutes),
            "n_ingredients": int(row.n_ingredients),
            "origin": str(row.origin)
        }
    return None


def query_retrieve_ingredients(graph: Graph, recipe_name: str):
    """
    Retorna os ingredients de uma receita pelo nome (uma).
    """
    needle = _esc(recipe_name)
    q = f"""
    SELECT ?ingredientLabel WHERE {{
        ?recipe rdf:type ex:Recipe .
        ?recipe rdfs:label ?label .
        FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{needle}")))
        ?recipe ex:hasIngredient ?ingredient .
        ?ingredient rdfs:label ?ingredientLabel .
    }}
    """
    return [str(r.ingredientLabel) for r in graph.query(q, initNs={"ex": EX, "rdf": RDF, "rdfs": RDFS})]


def query_get_prep_time(graph: Graph, recipe_name: str, top_k: int = 3):
    """
    Retorna recipe_name, n_steps, nutrition para top 3 receitas que correspondam ao nome.
    """
    needle = _esc(recipe_name)
    q = f"""
    SELECT ?recipe ?label ?n_steps ?nutrition WHERE {{
        ?recipe rdf:type ex:Recipe .
        ?recipe rdfs:label ?label .
        FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{needle}")))
        ?recipe ex:n_steps ?n_steps .
        ?recipe ex:hasNutrition ?nutrition .
    }} LIMIT {top_k}
    """
    results = []
    for row in graph.query(q, initNs={"ex": EX, "rdf": RDF, "rdfs": RDFS}):
        results.append({
            "recipe_uri": str(row.recipe),
            "recipe_name": str(row.label),
            "n_steps": int(row.n_steps),
            "nutrition": str(row.nutrition),
        })
    return results


def query_by_cooking_time(graph: Graph, minutes: int):
    """
    Retorna receitas que tenham ex:minutes igual ao tempo fornecido, com recipe_name, tag, n_steps, nutrition.
    Top 2.
    """
    q = f"""
    SELECT ?recipe ?label ?tagLabel ?n_steps ?nutrition WHERE {{
        ?recipe rdf:type ex:Recipe .
        ?recipe rdfs:label ?label .
        ?recipe ex:minutes {minutes} .
        ?recipe ex:n_steps ?n_steps .
        ?recipe ex:hasNutrition ?nutrition .
        ?recipe ex:hasTag ?tag .
        ?tag rdfs:label ?tagLabel .
    }} LIMIT 2
    """
    results = []
    for row in graph.query(q, initNs={"ex": EX, "rdf": RDF, "rdfs": RDFS}):
        results.append({
            "recipe_uri": str(row.recipe),
            "recipe_name": str(row.label),
            "tag": str(row.tagLabel),
            "n_steps": int(row.n_steps),
            "nutrition": str(row.nutrition)
        })
    return results
