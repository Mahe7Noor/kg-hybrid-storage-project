from pymongo import MongoClient
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch

# MongoDB
try:
    mongo = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
    mongo.server_info()
    print("✓ MongoDB connected")
except Exception as e:
    print(f"✗ MongoDB failed: {e}")

# Neo4j
try:
    neo4j = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))
    neo4j.verify_connectivity()
    print("✓ Neo4j connected")
except Exception as e:
    print(f"✗ Neo4j failed: {e}")

# Elasticsearch

    
try:
    es = Elasticsearch("http://localhost:9200")
    info = es.info()
    print(f"✓ Elasticsearch connected — version {info['version']['number']}")
except Exception as e:
    print(f"✗ Elasticsearch failed: {e}")