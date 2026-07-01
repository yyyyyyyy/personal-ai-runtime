import { lazy, Suspense } from "react";

const LazySyntaxBlock = lazy(async () => {
  const [{ Prism }, { oneDark }] = await Promise.all([
    import("react-syntax-highlighter"),
    import("react-syntax-highlighter/dist/esm/styles/prism"),
  ]);
  return {
    default: function SyntaxBlock({ language, code }: { language: string; code: string }) {
      return (
        <Prism style={oneDark} language={language} PreTag="div">
          {code}
        </Prism>
      );
    },
  };
});

export function CodeBlock({ language, code }: { language: string; code: string }) {
  return (
    <Suspense
      fallback={
        <pre className="bg-gray-900 rounded p-3 text-xs overflow-x-auto">
          <code>{code}</code>
        </pre>
      }
    >
      <LazySyntaxBlock language={language} code={code} />
    </Suspense>
  );
}
