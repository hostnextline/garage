-- Les fonctions de la correction rapide : seulement pour les personnes connectées du garage (comme toutes les autres).
-- (Sur Supabase, une nouvelle fonction est d'abord permise à tout le monde ; ici on l'enlève aux visiteurs sans compte.)
revoke execute on function public.doc_patch(text, jsonb, text[]), public.block_mark(text), public.block_take(text, bigint),
  public.block_book(text, bigint, text, jsonb, boolean), public.number_invoice(text) from public, anon;
grant execute on function public.doc_patch(text, jsonb, text[]), public.block_mark(text), public.block_take(text, bigint),
  public.block_book(text, bigint, text, jsonb, boolean), public.number_invoice(text) to authenticated, service_role;
