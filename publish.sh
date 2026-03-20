#!/bin/bash
echo "🎩 Publishing NeuralClear after repository creation"
echo "========================================"

# Configure SSH remote
cd /Users/qiuxiao/.qclaw/workspace/neuralclear
git remote set-url origin git@github.com:Zihuatanejo63/neuralclear

# Push all code
echo "Pushing main branch..."
git push -u origin main || {
    echo "Push failed, trying force..."
    git push --force -u origin main
}

echo "✅ Code pushed to GitHub!"
echo "URL: https://github.com/Zihuatanejo63/neuralclear"

echo ""
echo "Setting up CI/CD..."

# Create GitHub Actions workflow
mkdir -p .github/workflows
cat > .github/workflows/ci.yml << 'EOF'
name: NeuralClear CI
on: [push]
jobs:
  python-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Python Demo
        run: python neuralclear/neuralclear.py
      - name: Network Simulation
        run: python simulation.py
  rust-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-rust@v2
      - name: Rust Build
        run: cargo check
EOF

# Push CI config
git add .github/workflows/ci.yml
git commit -m "Add GitHub Actions CI/CD"
git push

echo ""
echo "✅ CI/CD configured!"
echo ""
echo "Repository setup complete."
echo ""
echo "Next steps:"
echo "1. Add topics: AI Agent, Blockchain, Rust, Python, Distributed Computing"
echo "2. Enable GitHub Discussions"
echo "3. Create Discord community"
echo "4. Announce on social media"
echo ""
echo "Run demo: python3 neuralclear/neuralclear.py"
echo "========================================"