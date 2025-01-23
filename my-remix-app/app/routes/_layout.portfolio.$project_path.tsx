import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import { getXataClient } from "~/lib/xata";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";

export async function loader({ params }: LoaderFunctionArgs) {
  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const projectPath = `portfolio/${params.project_path}`;
  const project = await xata.db.contents
    .filter({ url_path: projectPath })
    .select(["title", "content", "meta", "xata_id"])
    .getFirst();

  if (!project) {
    throw new Response("Project not found", { status: 404 });
  }

  return json({ project });
}

export default function ProjectDetails() {
  const { project } = useLoaderData<typeof loader>();
  const gallery = (project.meta as { gallery?: string[] })?.gallery || [];

  return (
    <main className="container mx-auto px-4 py-12 flex-grow">
      <div className="max-w-4xl mx-auto">
        {/* Project Header */}
        <header className="mb-8">
          <h1 className="text-4xl font-bold mb-4 text-gray-900">
            {project.title}
          </h1>
          {(project.meta as { coverImage?: string })?.coverImage && (
            <img
              src={(project.meta as { coverImage?: string }).coverImage}
              alt={`Cover for ${project.title}`}
              className="w-full h-64 object-cover rounded-lg shadow-md mb-6"
            />
          )}
        </header>

        {/* Project Content */}
        <article className="bg-white rounded-lg shadow-md p-8 mb-12">
          <div className="prose prose-lg max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
            >
              {project.content?.current}
            </ReactMarkdown>
          </div>
        </article>

        {/* Project Gallery */}
        {gallery.length > 0 && (
          <section>
            <h2 className="text-2xl font-bold mb-6 text-gray-900">
              Project Gallery
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {gallery.map((imageUrl, index) => (
                <div
                  key={`${project.xata_id}-gallery-${index}`}
                  className="aspect-video relative group overflow-hidden rounded-lg shadow-md"
                >
                  <img
                    src={imageUrl}
                    alt={`Screenshot ${index + 1} of ${project.title}`}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
