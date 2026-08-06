export default function JsonView({ data }: { data: unknown }) {
  return (
    <pre className="mt-2 max-h-80 overflow-auto rounded bg-gray-900 p-3 font-mono text-xs text-green-300">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
