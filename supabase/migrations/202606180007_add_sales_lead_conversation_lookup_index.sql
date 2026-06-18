create index if not exists idx_oom_sakkie_sales_leads_conversation_created
    on public.oom_sakkie_sales_leads(chatwoot_conversation_id, created_at desc)
    where chatwoot_conversation_id <> '';
