import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import { getXataClient } from "~/lib/xata";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";

export async function loader({ request }: LoaderFunctionArgs) {
  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const resume = await xata.db.contents
    .filter({ url_path: "/resume/current" })
    .select(["title", "content", "xata_id"])
    .getFirst();

  if (!resume) {
    throw new Response("Resume not found", { status: 404 });
  }

  return json({ resume });
}

export default function CurrentResume() {
  const { resume } = useLoaderData<typeof loader>();

  return (
    <main className="container mx-auto px-4 py-12 flex-grow">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-8 text-gray-900">
          {resume.title || "Current Resume"}
        </h1>
        <article className="bg-white rounded-lg shadow-md p-8">
          <div className="prose prose-lg max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
            >
              {resume.content?.current}
            </ReactMarkdown>
          </div>
        </article>
      </div>
    </main>
  );
}
