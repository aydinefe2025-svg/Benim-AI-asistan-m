from core.doi_priority import prioritize_requested_doi


def execute_targeted_research(manager, task, client, model, lookup):
    def search(query, limit=3):
        return prioritize_requested_doi(task, lookup(query, limit=limit))

    return manager.execute(task, client=client, model=model, source_lookup=search)
