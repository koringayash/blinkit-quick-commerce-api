# QuickKart - one-command workflows.
# Requires Docker (with Compose v2) and GNU make.
# Windows: use Git Bash / WSL, or `choco install make`. Without make, run the
# `docker compose ...` commands shown next to each target directly.

COMPOSE      := docker compose
COMPOSE_DEV  := docker compose -f docker-compose.yml -f docker-compose.dev.yml

.DEFAULT_GOAL := help
.PHONY: help env up build start down restart logs logs-backend logs-frontend ps \
        dev dev-down db-shell backend-shell frontend-shell clean rebuild \
        k8s-up k8s-down k8s-status k8s-logs k8s-psql k8s-port-forward

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example (if missing)
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

up: env ## Build & start the whole stack in the background (prod images)
	$(COMPOSE) up --build -d
	@echo ""
	@echo "  Frontend : http://localhost:3000"
	@echo "  API      : http://localhost:8000   (docs: http://localhost:8000/docs)"
	@echo "  Logins   : demo@quickkart.com / demo1234   |   admin@quickkart.com / admin1234"

build: ## Build all images without starting them
	$(COMPOSE) build

start: ## Start existing containers without rebuilding
	$(COMPOSE) up -d

down: ## Stop and remove containers (keeps the database volume)
	$(COMPOSE) down

restart: ## Restart all services
	$(COMPOSE) restart

rebuild: ## Rebuild images from scratch (no cache) and start
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

logs: ## Follow logs of all services
	$(COMPOSE) logs -f --tail=100

logs-backend: ## Follow backend logs
	$(COMPOSE) logs -f --tail=100 backend

logs-frontend: ## Follow frontend logs
	$(COMPOSE) logs -f --tail=100 frontend

ps: ## Show service status & health
	$(COMPOSE) ps

dev: env ## Run with hot reload (frontend :8080, backend :8000)
	$(COMPOSE_DEV) up --build

dev-down: ## Stop the dev stack
	$(COMPOSE_DEV) down

db-shell: ## Open psql inside the database container
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

backend-shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend sh

frontend-shell: ## Open a shell in the frontend container
	$(COMPOSE) exec frontend sh

clean: ## Stop everything AND delete the database volume (re-seeds on next start)
	$(COMPOSE_DEV) down -v --remove-orphans

# --- Kubernetes (kubectl + Kustomize) ---
k8s-up: ## Deploy all Kubernetes manifests (Namespace, ConfigMap, Secret, Postgres, Backend, Frontend, Gateway, Ingress, DB-Client)
	kubectl apply -k k8s/
	kubectl -n quickkart rollout status statefulset/postgres --timeout=120s
	kubectl -n quickkart rollout status deployment/backend --timeout=120s
	kubectl -n quickkart rollout status deployment/frontend --timeout=120s
	kubectl -n quickkart rollout status deployment/gateway --timeout=120s

k8s-down: ## Delete all QuickKart Kubernetes resources
	kubectl delete -k k8s/ --ignore-not-found

k8s-status: ## Show Pods, Services, PVCs, HPAs, and Ingress in the quickkart namespace
	kubectl -n quickkart get pods,svc,pvc,hpa,ingress

k8s-logs: ## Tail logs from backend and frontend Pods in Kubernetes
	kubectl -n quickkart logs -f -l app.kubernetes.io/part-of=quickkart --all-containers=true --max-log-requests=10

k8s-psql: ## Open an interactive psql shell inside the Kubernetes db-client Pod
	kubectl -n quickkart exec -it db-client -- psql

k8s-port-forward: ## Forward the Kubernetes Nginx gateway Service to http://localhost:8080
	kubectl -n quickkart port-forward svc/gateway 8080:80

