import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import { getXataClient } from "~/lib/xata";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

export async function loader({ params }: LoaderFunctionArgs) {
  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const { category, post_path } = params;
  const fullPath = `/blog/${category}/${post_path}`;

  console.log("Fetching blog post:", { fullPath });
  const post = await xata.db.contents
    .filter({
      url_path: fullPath,
      category: "blog",
    })
    .select([
      "title",
      "url_path",
      "content",
      "meta",
      "category",
      "xata_createdat",
    ])
    .getFirst();

  console.log("Found post:", post);
  if (!post) {
    throw new Response("Not Found", { status: 404 });
  }

  return json({ post });
}

export default function BlogPost() {
  const { post } = useLoaderData<typeof loader>();
  const content = post.content?.current || "";

  return (
    <main className="container mx-auto px-4 py-12 flex-grow">
      <article className="prose prose-lg mx-auto">
        <header className="mb-8">
          <h1 className="text-4xl font-bold mb-4">{post.title}</h1>
          {post.xata_createdat && (
            <time className="text-gray-600">
              {new Date(post.xata_createdat).toLocaleDateString()}
            </time>
          )}
        </header>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          className="prose prose-lg"
        >
          {content}
        </ReactMarkdown>
      </article>
    </main>
  );
}
