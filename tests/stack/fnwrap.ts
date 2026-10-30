// local only: runs a Supabase edge function on its own port
const orig = Deno.serve.bind(Deno);
const port = Number(Deno.env.get('LOCAL_PORT'));
Object.defineProperty(Deno, 'serve', { value: (h: any) => orig({ port, hostname: '127.0.0.1', onListen() {} }, h), configurable: true, writable: true });
await import(Deno.env.get('FN_FILE')!);
