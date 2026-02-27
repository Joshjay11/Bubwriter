export default function ProjectPage({ params }: { params: { id: string } }) {
  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">Writing Workspace</h1>
      <p className="text-foreground/70">Project {params.id} — Coming Soon</p>
    </div>
  );
}
