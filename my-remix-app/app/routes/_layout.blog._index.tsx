import { json } from "@remix-run/node";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData, Link } from "@remix-run/react";
import { getXataClient } from "~/lib/xata";

export async function loader({ request }: LoaderFunctionArgs) {
  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const blogPosts = await xata.db.contents
    .filter({
      category: "blog",
    })
    .select([
      "title",
      "url_path",
      "xata_id",
      "content",
      "meta",
      "category",
      "xata_createdat",
    ])
    .sort("xata_createdat", "desc")
    .getMany();

  console.log("Found blog posts:", blogPosts);

  return json({ blogPosts });
}

export default function BlogIndex() {
  const { blogPosts } = useLoaderData<typeof loader>();

  return (
    <main className="container mx-auto px-4 py-12 flex-grow">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900">Blog Posts</h1>
          <Link
            to="/blog/new"
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
          >
            New Post
          </Link>
        </div>

        {/* Blog Posts Grid */}
        <div className="space-y-6">
          {blogPosts.map((post) => {
            // Get subcategory from meta if available
            const subcategory =
              (post.meta as { subcategory?: string })?.subcategory || "General";

            return (
              <Link
                key={post.xata_id}
                to={post.url_path || "#"}
                className="block"
              >
                <article className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-sm font-medium px-3 py-1 bg-blue-100 text-blue-800 rounded-full">
                      {subcategory}
                    </span>
                    {post.xata_createdat && (
                      <time className="text-gray-600">
                        {new Date(post.xata_createdat).toLocaleDateString()}
                      </time>
                    )}
                  </div>
                  <h2 className="text-xl font-semibold mb-2 text-gray-900">
                    {post.title || "Untitled Post"}
                  </h2>
                  <p className="text-gray-600 line-clamp-2">
                    {(post.meta as { description?: string })?.description ||
                      "No description available"}
                  </p>
                </article>
              </Link>
            );
          })}
        </div>
      </div>
    </main>
  );
}
