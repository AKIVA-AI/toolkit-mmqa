# Multimodal Dataset QA - Quick Start

## 🚀 Installation

```bash
pip install -e ".[dev]"
toolkit-mmqa --version
```

## 📝 Basic Usage

```bash
# Scan dataset for duplicates
toolkit-mmqa scan --root datasets/my-dataset --out report.json
```

## 🐳 Docker Usage

```bash
docker-compose up -d
docker-compose exec multimodal-qa toolkit-mmqa scan --root /app/datasets/my-dataset
```

## 📚 Next Steps

- Read [README.md](README.md)
- Check [DEPLOYMENT.md](DEPLOYMENT.md)

---

**Ready to ensure dataset quality!** 🚀
