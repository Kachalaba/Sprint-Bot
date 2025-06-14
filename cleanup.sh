#!/bin/bash
set -e

# Files to remove
FILES=(
    "План развития Sprint-Bot в систему секундомера тренера.pdf"
    "Screenshot_1555.png"
)

for file in "${FILES[@]}"; do
    if [ -e "$file" ]; then
        # Remove from git tracking if tracked
        git rm -f --cached "$file" >/dev/null 2>&1 || true
        rm -f "$file"
        echo "Removed $file"
    fi
done

# Update .gitignore with additional rules if they are not present
IGNORE_BLOCK="\n# Документы и изображения\n*.pdf\n*.png\n*.jpg\n*.jpeg\n*.gif\n\n# Файлы IDE и системные файлы\n.idea/\n.vscode/\n*.suo\n.DS_Store\n"

if ! grep -q "# Документы и изображения" .gitignore 2>/dev/null; then
    printf "%b" "$IGNORE_BLOCK" >> .gitignore
    echo ".gitignore updated"
fi

echo "Очистка завершена. Проверьте изменения (git status) и сделайте коммит."
