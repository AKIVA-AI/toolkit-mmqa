# Multimodal Dataset QA - Deployment Guide

## ðŸš€ Quick Start

### Docker Deployment (Recommended)

```bash
cd multimodal-dataset-qa
docker-compose up -d
docker-compose exec multimodal-qa toolkit-mmqa scan --root datasets/my-dataset
```

### Local Installation

```bash
pip install -e ".[dev]"
toolkit-mmqa --version
pytest
```

## ðŸ”§ Configuration

See `.env.example` for all options.

**Key Settings:**
- `CHECK_IMAGE_QUALITY`: Enable image quality checks
- `CHECK_TEXT_QUALITY`: Enable text quality checks
- `CHECK_CONSISTENCY`: Enable consistency checks

## ðŸ“Š Production Deployment

### CI/CD Integration

```yaml
- name: Check Dataset Quality
  run: toolkit-mmqa scan --root $DATASET_PATH
```

### Monitoring

```bash
# Run a scan and inspect the JSON report for dataset health
toolkit-mmqa scan --root $DATASET_PATH --out report.json
```

## ðŸ“ž Support

- Documentation: [README.md](README.md)
- Support: <support-email>



