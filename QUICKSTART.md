# Multimodal Dataset QA - Quick Start

## 🚀 Installation

```bash
pip install -e ".[dev]"
toolkit-mmqa --version
```

## 📝 Basic Usage

```bash
# Check dataset quality
toolkit-mmqa check --dataset datasets/my-dataset --out report.json
```

## 🐳 Docker Usage

```bash
docker-compose up -d
docker-compose exec multimodal-qa toolkit-mmqa check --dataset /app/datasets/my-dataset
```

## 📚 Next Steps

- Read [README.md](README.md)
- Check [DEPLOYMENT.md](DEPLOYMENT.md)

---

**Ready to ensure dataset quality!** 🚀
