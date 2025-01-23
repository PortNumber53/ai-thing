import { json, redirect } from "@remix-run/node";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import {
  Form,
  useActionData,
  useLoaderData,
  useNavigation,
} from "@remix-run/react";
import { getXataClient } from "~/lib/xata";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";

export async function loader({ params }: LoaderFunctionArgs) {
  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const { category, post_path } = params;
  const fullPath = `/blog/${category}/${post_path}`;

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

  if (!post) {
    throw new Response("Not Found", { status: 404 });
  }

  return json({ post });
}

export async function action({ request, params }: ActionFunctionArgs) {
  const formData = await request.formData();
  const title = formData.get("title") as string;
  const content = formData.get("content") as string;
  const description = formData.get("description") as string;

  const { category, post_path } = params;
  const fullPath = `/blog/${category}/${post_path}`;

  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const post = await xata.db.contents
    .filter({
      url_path: fullPath,
      category: "blog",
    })
    .getFirst();

  if (!post) {
    throw new Response("Not Found", { status: 404 });
  }

  await xata.db.contents.update(post.xata_id, {
    title,
    content: { current: content },
    meta: { ...post.meta, description },
  });

  return redirect(fullPath);
}

export default function EditBlogPost() {
  const { post } = useLoaderData<typeof loader>();
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const [content, setContent] = useState(post.content?.current || "");
  const description =
    (post.meta as { description?: string })?.description || "";
  const isSubmitting = navigation.state === "submitting";

  return (
    <main className="container mx-auto px-4 py-12 flex-grow">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">Edit Post</h1>
        </div>
        <Form method="post" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Left Column - Editor */}
            <div className="space-y-6">
              <div>
                <label
                  htmlFor="title"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Title
                </label>
                <input
                  type="text"
                  name="title"
                  id="title"
                  defaultValue={post.title || ""}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors bg-white text-gray-900"
                  required
                />
              </div>

              <div>
                <label
                  htmlFor="description"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Description
                </label>
                <input
                  type="text"
                  name="description"
                  id="description"
                  defaultValue={description}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors bg-white text-gray-900"
                />
              </div>

              <div>
                <label
                  htmlFor="content"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Content
                </label>
                <div className="relative">
                  <textarea
                    name="content"
                    id="content"
                    rows={30}
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 rounded-md shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors bg-white text-gray-900 font-mono"
                    required
                  />
                  <div className="absolute bottom-3 right-3 text-xs text-gray-500">
                    Markdown supported
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-4">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? (
                    <>
                      <svg
                        className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                        aria-label="Loading"
                        role="img"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                      </svg>
                      Saving...
                    </>
                  ) : (
                    <>
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-4 w-4 mr-1"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        aria-label="Save changes"
                        role="img"
                      >
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                      Save Changes
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Right Column - Preview */}
            <div className="bg-gray-50 rounded-lg p-6 border border-gray-200">
              <div className="prose prose-lg max-w-none">
                <h1>{post.title || "Untitled Post"}</h1>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeRaw]}
                >
                  {content}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        </Form>
      </div>
    </main>
  );
}
