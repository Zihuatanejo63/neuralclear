#!/bin/bash
# NeuralClear Re-Publisher - Clean Install

echo "🎩 NeuralClean Clean Re-Publisher"
echo "========================================"

# Reset Git
cd /Users/qiuxiao/.qclaw/workspace/neuralclear
rm -rf .git
git init

# Add all files
git add -A
git commit -m "Initial commit: NeuralClear AI Agent Protocol"

# Configure remote (ensure it's Zihuatanejo63)
git remote add origin git@github.com:Zihuatanejo63/neuralclear

# Verify SSH authentication
echo "Verifying SSH auth..."
if ssh -T git@github.com 2>&1 | grep -q "Hi Zihuatanejo63"; then
    echo "✅ SSH authenticated for Zihuatanejo63"
else
    echo "✗ SSH authentication failed"
    echo "Please add SSH key to GitHub:"
    echo ""
    cat ~/.ssh/id_zihuatanejo63.pub
    echo ""
    echo "Go to: https://github.com/settings/keys"
    exit 1
fi

# Check if repository exists
echo "Checking repository..."
curl -s "https://api.github.com/repos/Zihuatanejo63/neuralclear" > /tmp/repo_check.json
if grep -q "Not Found" /tmp/repo_check.json; then
    echo "Repository not found. Please create it at:"
    echo "https://github.com/new"
    echo ""
    echo "Owner: Zihuatanejo63"
    echo "Name: neuralclear"
    echo "Description: AI Agent to Agent Trading Protocol"
    echo "Public: Yes"
    echo "Initialize: No"
    echo ""
    echo "After creation, run this script again."
    exit 1
fi

# Push code
echo "Pushing code..."
git push -u origin main || {
    echo "Push failed. Please ensure repository exists."
    exit 1
}

# Setup CI/CD
mkdir -p .github/workflows
cat > .github/workflows/ci.yml << 'EOF'
name: NeuralClear CI
on: [push]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Demo Test
        run: python neuralclear/neuralclear.py
      - name: Simulation Test
        run: python simulation.py
EOF

git add .github/workflows/ci.yml
git commit -m "Add GitHub Actions CI/CD"
git push

echo ""
echo "✅ NeuralClear successfully published!"
echo "URL: https://github.com/Zihuatanejo63/neuralclear"
echo ""
echo "Run demo: python3 neuralclear/neuralclear.py"
echo "========================================"