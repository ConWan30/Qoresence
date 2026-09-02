export function AppErrorComponent({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <main className="p-6 font-mono text-sm text-veto">
      <p>Sight Glass failed to render.</p>
      <p className="mt-2 text-muted-foreground">{msg}</p>
    </main>
  );
}
