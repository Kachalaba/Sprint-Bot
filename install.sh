#!/usr/bin/env bash
set -euo pipefail

SUDO=""

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

ensure_sudo() {
    if command_exists sudo; then
        SUDO="sudo"
    elif [ "$(id -u)" -eq 0 ]; then
        SUDO=""
    else
        echo "Для установки пакетов требуется sudo или запуск от имени root." >&2
        exit 1
    fi
}

install_docker_linux() {
    echo "Docker не найден. Устанавливаю Docker..."
    ensure_sudo
    $SUDO apt-get update
    $SUDO apt-get install -y ca-certificates curl gnupg lsb-release
    if ! command_exists docker; then
        if ! [ -f /etc/apt/keyrings/docker.gpg ]; then
            $SUDO install -m 0755 -d /etc/apt/keyrings
            curl -fsSL "https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg" | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
        fi
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") $(lsb_release -cs) stable" | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
        $SUDO apt-get update
        $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io
    else
        $SUDO apt-get install -y docker.io
    fi
}

install_docker_compose_linux() {
    echo "docker-compose не найден. Устанавливаю docker-compose..."
    ensure_sudo
    if $SUDO apt-get install -y docker-compose; then
        return
    fi
    $SUDO apt-get install -y docker-compose-plugin
    if ! command_exists docker-compose && [ -x /usr/libexec/docker/cli-plugins/docker-compose ]; then
        $SUDO ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose
    fi
}

install_docker_macos() {
    echo "Docker не найден. Устанавливаю Docker через Homebrew..."
    if ! command_exists brew; then
        echo "Homebrew не установлен. Пожалуйста, установите Homebrew и повторите попытку." >&2
        exit 1
    fi
    brew install --cask docker
}

install_docker_compose_macos() {
    echo "docker-compose не найден. Устанавливаю docker-compose через Homebrew..."
    if ! command_exists brew; then
        echo "Homebrew не установлен. Пожалуйста, установите Homebrew и повторите попытку." >&2
        exit 1
    fi
    brew install docker-compose
}

create_docker_compose_wrapper() {
    local target="/usr/local/bin/docker-compose"
    echo "Создаю обёртку для docker compose plugin..."
    if command_exists sudo; then
        printf '#!/usr/bin/env bash\nexec docker compose "$@"\n' | sudo tee "$target" >/dev/null
        sudo chmod +x "$target"
    elif [ "$(id -u)" -eq 0 ]; then
        printf '#!/usr/bin/env bash\nexec docker compose "$@"\n' > "$target"
        chmod +x "$target"
    else
        echo "Недостаточно прав для создания docker-compose." >&2
        exit 1
    fi
}

ensure_docker() {
    if command_exists docker; then
        echo "Docker уже установлен."
        return
    fi
    case "$(uname -s)" in
        Linux)
            install_docker_linux
            ;;
        Darwin)
            install_docker_macos
            ;;
        *)
            echo "Неизвестная ОС. Пожалуйста, установите Docker вручную." >&2
            exit 1
            ;;
    esac
}

ensure_docker_compose() {
    if command_exists docker-compose; then
        echo "docker-compose уже установлен."
        return
    fi
    if command_exists docker && docker compose version >/dev/null 2>&1; then
        create_docker_compose_wrapper
        return
    fi
    case "$(uname -s)" in
        Linux)
            install_docker_compose_linux
            ;;
        Darwin)
            install_docker_compose_macos
            ;;
        *)
            echo "Неизвестная ОС. Пожалуйста, установите docker-compose вручную." >&2
            exit 1
            ;;
    esac
}

update_env_value() {
    local key="$1"
    local value="$2"
    local escaped_value
    escaped_value=$(printf '%s\n' "$value" | sed -e 's/[\/&]/\\&/g')
    case "$(uname -s)" in
        Darwin)
            sed -i '' "s/^${key}=.*/${key}=${escaped_value}/" .env
            ;;
        *)
            sed -i "s/^${key}=.*/${key}=${escaped_value}/" .env
            ;;
    esac
}

main() {
    ensure_docker
    ensure_docker_compose

    local script_dir
    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    cd "$script_dir"

    local repo_dir="$script_dir"
    if [ ! -f "$repo_dir/docker-compose.yml" ] || [ ! -f "$repo_dir/.env.example" ]; then
        repo_dir="$script_dir/Sprint-Bot"
        if [ ! -d "$repo_dir" ]; then
            echo "Клонирую репозиторий Sprint-Bot..."
            git clone https://github.com/Kachalaba/Sprint-Bot.git "$repo_dir"
        fi
        cd "$repo_dir"
    else
        cd "$repo_dir"
    fi

    if [ ! -f .env.example ]; then
        echo ".env.example не найден. Проверьте репозиторий." >&2
        exit 1
    fi

    cp .env.example .env

    read -rp "Введите BOT_TOKEN: " BOT_TOKEN
    read -rp "Введите ADMIN_IDS (через запятую): " ADMIN_IDS

    update_env_value "BOT_TOKEN" "$BOT_TOKEN"
    update_env_value "ADMIN_IDS" "$ADMIN_IDS"

    docker-compose up -d --build

    echo "Sprint-Bot успешно запущен!"
}

main "$@"
