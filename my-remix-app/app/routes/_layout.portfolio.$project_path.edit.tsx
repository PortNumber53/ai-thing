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

interface ProjectMeta {
  description?: string;
  coverImage?: string;
  gallery?: string[];
}

interface FormContent {
  title: string;
  body: string;
  meta: ProjectMeta;
}

interface ValidationErrors {
  title?: string;
  body?: string;
  description?: string;
  coverImage?: string;
  general?: string;
}

interface ActionData {
  errors?: ValidationErrors;
  content?: FormContent;
}

// Validation function for portfolio content
function validateContent(content: FormContent): ValidationErrors | null {
  const errors: ValidationErrors = {};

  if (!content.title?.trim()) {
    errors.title = "Title is required";
  }

  if (!content.body?.trim()) {
    errors.body = "Content is required";
  }

  if (!content.meta.description?.trim()) {
    errors.description = "Description is required";
  }

  if (!content.meta.coverImage?.trim()) {
    errors.coverImage = "Cover image URL is required";
  }

  return Object.keys(errors).length > 0 ? errors : null;
}

export async function loader({ params }: LoaderFunctionArgs) {
  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const projectPath = `portfolio/${params.project_path}`;
  const project = await xata.db.contents
    .filter({ url_path: projectPath })
    .select(["*"])
    .getFirst();

  if (!project) {
    throw new Response("Project not found", { status: 404 });
  }

  return json({ project });
}

export async function action({ request, params }: ActionFunctionArgs) {
  const xata = getXataClient();
  if (!xata) {
    throw new Error("Xata client not initialized");
  }

  const formData = await request.formData();
  const projectPath = `portfolio/${params.project_path}`;

  const content: FormContent = {
    title: formData.get("title")?.toString() || "",
    body: formData.get("body")?.toString() || "",
    meta: {
      description: formData.get("description")?.toString(),
      coverImage: formData.get("coverImage")?.toString(),
      gallery: formData.get("gallery")?.toString()?.split("\n").filter(Boolean),
    },
  };

  // Validate content
  const validationErrors = validateContent(content);
  if (validationErrors) {
    return json<ActionData>(
      { errors: validationErrors, content },
      { status: 400 }
    );
  }

  try {
    // Update or create the project
    const existing = await xata.db.contents
      .filter({ url_path: projectPath })
      .getFirst();

    if (existing) {
      await xata.db.contents.update(existing.xata_id, {
        title: content.title,
        content: { current: content.body },
        meta: content.meta,
      });
    } else {
      await xata.db.contents.create({
        title: content.title,
        content: { current: content.body },
        meta: content.meta,
        url_path: projectPath,
      });
    }

    return redirect(`/portfolio/${params.project_path}`);
  } catch (error) {
    return json<ActionData>(
      {
        errors: {
          general: "Failed to save project",
        },
        content,
      },
      { status: 500 }
    );
  }
}

export default function EditProject() {
  const { project } = useLoaderData<typeof loader>();
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const isSubmitting = navigation.state === "submitting";

  // Form state
  const [title, setTitle] = useState(
    actionData?.content?.title || project.title || ""
  );
  const [description, setDescription] = useState(
    actionData?.content?.meta?.description ||
      (project.meta as ProjectMeta)?.description ||
      ""
  );
  const [coverImage, setCoverImage] = useState(
    actionData?.content?.meta?.coverImage ||
      (project.meta as ProjectMeta)?.coverImage ||
      ""
  );
  const [gallery, setGallery] = useState(
    actionData?.content?.meta?.gallery?.join("\n") ||
      ((project.meta as ProjectMeta)?.gallery || []).join("\n") ||
      ""
  );
  const [markdownContent, setMarkdownContent] = useState(
    actionData?.content?.body || project.content?.current || ""
  );

  return (
    <Form method="post" className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <div className="flex justify-between items-center mb-6">
            <h1 className="text-2xl font-bold text-gray-900">Edit Project</h1>
            <div className="flex items-center space-x-4">
              <button
                type="submit"
                disabled={isSubmitting}
                className={`px-4 py-2 rounded text-white transition-colors ${
                  isSubmitting ? "bg-blue-400" : "bg-blue-600 hover:bg-blue-700"
                }`}
              >
                {isSubmitting ? "Saving..." : "Save Project"}
              </button>
            </div>
          </div>

          {/* Title */}
          <div className="mb-6">
            <label
              htmlFor="title"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Title
            </label>
            <input
              id="title"
              type="text"
              name="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded"
            />
            {actionData?.errors?.title && (
              <p className="text-red-600 text-sm mt-1">
                {actionData.errors.title}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="mb-6">
            <label
              htmlFor="description"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Description
            </label>
            <textarea
              id="description"
              name="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full p-2 border border-gray-300 rounded"
            />
            {actionData?.errors?.description && (
              <p className="text-red-600 text-sm mt-1">
                {actionData.errors.description}
              </p>
            )}
          </div>

          {/* Cover Image URL */}
          <div className="mb-6">
            <label
              htmlFor="coverImage"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Cover Image URL
            </label>
            <input
              id="coverImage"
              type="text"
              name="coverImage"
              value={coverImage}
              onChange={(e) => setCoverImage(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded"
            />
            {actionData?.errors?.coverImage && (
              <p className="text-red-600 text-sm mt-1">
                {actionData.errors.coverImage}
              </p>
            )}
            {coverImage && (
              <img
                src={coverImage}
                alt="Cover preview"
                className="mt-2 max-h-40 object-cover rounded"
              />
            )}
          </div>

          {/* Gallery URLs */}
          <div className="mb-6">
            <label
              htmlFor="gallery"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Gallery Image URLs (one per line)
            </label>
            <textarea
              id="gallery"
              name="gallery"
              value={gallery}
              onChange={(e) => setGallery(e.target.value)}
              rows={4}
              className="w-full p-2 border border-gray-300 rounded"
              placeholder="https://example.com/image1.jpg&#10;https://example.com/image2.jpg"
            />
          </div>
        </div>

        {/* Content Editor */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Markdown Input */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <label
              htmlFor="body"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Content (Markdown)
            </label>
            <textarea
              id="body"
              name="body"
              value={markdownContent}
              onChange={(e) => setMarkdownContent(e.target.value)}
              rows={20}
              className="w-full p-2 border border-gray-300 rounded font-mono"
            />
            {actionData?.errors?.body && (
              <p className="text-red-600 text-sm mt-1">
                {actionData.errors.body}
              </p>
            )}
          </div>

          {/* Preview */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-sm font-medium text-gray-700 mb-2">Preview</h2>
            <div className="prose max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeRaw]}
              >
                {markdownContent}
              </ReactMarkdown>
            </div>
          </div>
        </div>
      </div>
    </Form>
  );
}
