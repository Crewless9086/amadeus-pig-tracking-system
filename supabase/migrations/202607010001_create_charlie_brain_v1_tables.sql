create table if not exists public.charlie_brain_documents (
    document_id text primary key,
    doc_path text not null unique,
    title text not null,
    entity_key text not null default 'charlie_core',
    document_type text not null default 'truth_doc',
    status text not null default 'active',
    summary text,
    tags jsonb not null default '[]'::jsonb,
    owner_approved boolean not null default false,
    confidence_level text not null default 'working',
    last_reviewed_at timestamptz,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.charlie_project_memory (
    memory_id text primary key,
    project_key text not null,
    entity_key text not null,
    memory_type text not null,
    title text not null,
    summary text,
    status text not null default 'active',
    source_document_id text references public.charlie_brain_documents(document_id) on delete set null,
    source_mission_id text references public.charlie_missions(mission_id) on delete set null,
    evidence_json jsonb not null default '{}'::jsonb,
    open_decisions jsonb not null default '[]'::jsonb,
    risks jsonb not null default '[]'::jsonb,
    metadata_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.charlie_mission_brain_context (
    context_id text primary key,
    mission_id text not null references public.charlie_missions(mission_id) on delete cascade,
    document_id text references public.charlie_brain_documents(document_id) on delete set null,
    memory_id text references public.charlie_project_memory(memory_id) on delete set null,
    relevance text not null default 'active_truth',
    reason text,
    loaded_by_agent text,
    created_at timestamptz not null default now()
);

create index if not exists idx_charlie_brain_documents_entity_status
    on public.charlie_brain_documents(entity_key, status, document_type);

create index if not exists idx_charlie_project_memory_project_status
    on public.charlie_project_memory(project_key, status, memory_type);

create index if not exists idx_charlie_mission_brain_context_mission
    on public.charlie_mission_brain_context(mission_id, created_at desc);

insert into app_private.migration_log (migration_id, description)
values (
    '202607010001_create_charlie_brain_v1_tables',
    'Create CHARLIE Brain v1 document registry, project memory, and mission brain-context link tables.'
)
on conflict (migration_id) do nothing;
