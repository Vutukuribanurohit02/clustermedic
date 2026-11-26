.RECIPEPREFIX = >
.PHONY: up down status health logs

up:        ## start Slurm first (it owns the network), then our stack
> $(MAKE) -C infra/slurm up
> docker compose up -d --build

down:
> docker compose down
> $(MAKE) -C infra/slurm down

status:
> docker compose ps
> docker exec slurmctld sinfo

health:
> ./scripts/healthcheck.sh

logs:
> docker compose logs -f --tail=50
