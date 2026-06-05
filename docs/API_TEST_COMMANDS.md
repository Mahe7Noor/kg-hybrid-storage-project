# API Test Commands

Run these after starting the backend:

```bash
curl http://127.0.0.1:8000/health
```

```bash
curl -X POST http://127.0.0.1:8000/ingest-sample
```

```bash
curl http://127.0.0.1:8000/documents
```

```bash
curl "http://127.0.0.1:8000/search?q=machine%20learning"
```

```bash
curl "http://127.0.0.1:8000/graph/entity/Dr.%20Smith"
```

```bash
curl "http://127.0.0.1:8000/hybrid-search?q=machine%20learning"
```

```bash
curl -X DELETE http://127.0.0.1:8000/reset-demo
```
