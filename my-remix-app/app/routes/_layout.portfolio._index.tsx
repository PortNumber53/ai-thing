import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData, Link } from "@remix-run/react";
import { getXataClient } from "~/lib/xata";

export async function loader({ request }: LoaderFunctionArgs) {
  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const projects = await xata.db.contents
    .filter({ url_path: { $startsWith: "portfolio/" } })
    .select(["title", "url_path", "xata_id", "content", "meta"])
    .getMany();

  return json({ projects });
}

export default function PortfolioIndex() {
  const { projects } = useLoaderData<typeof loader>();

  return (
    <main className="container mx-auto px-4 py-12 flex-grow">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-8 text-gray-900">Portfolio</h1>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {projects.map((project) => {
            const projectPath =
              project.url_path?.replace("portfolio/", "") || "";
            const coverImage = (project.meta as { coverImage?: string })
              ?.coverImage;

            return (
              <Link
                key={project.xata_id}
                to={`/portfolio/${projectPath}`}
                className="group block"
              >
                <article className="bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow">
                  {coverImage && (
                    <div className="aspect-video w-full overflow-hidden">
                      <img
                        src={coverImage}
                        alt={`Cover for ${project.title}`}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                    </div>
                  )}
                  <div className="p-6">
                    <h2 className="text-xl font-semibold mb-2 text-gray-900">
                      {project.title || "Untitled Project"}
                    </h2>
                    <p className="text-gray-600 line-clamp-2">
                      {(project.meta as { description?: string })
                        ?.description || "No description available"}
                    </p>
                  </div>
                </article>
              </Link>
            );
          })}
        </div>
      </div>
    </main>
  );
}
