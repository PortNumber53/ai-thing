import { MetaFunction, ActionFunctionArgs, redirect } from "@remix-run/node";
import { Form, useActionData } from "@remix-run/react";
import { saveContent } from "~/lib/xata";

export const meta: MetaFunction = () => {
  return [
    { title: "New Blog Entry" },
    {
      name: "description",
      content: "Create a new blog entry",
    },
  ];
};

export async function action({ request }: ActionFunctionArgs) {
  const formData = await request.formData();
  const title = formData.get("title") as string;
  const body = formData.get("body") as string;
  const url_path = formData.get("url_path") as string;

  await saveContent(url_path, { title, body });

  return redirect(`/dashboard/blog`);
}

export default function NewBlogEntry() {
  const actionData = useActionData();

  return (
    <div className="container mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-4">New Blog Entry</h1>
      <Form method="post">
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700">
            Title
          </label>
          <input
            type="text"
            name="title"
            className="mt-1 block w-full"
            required
          />
        </div>
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700">
            URL Path
          </label>
          <input
            type="text"
            name="url_path"
            className="mt-1 block w-full"
            required
          />
        </div>
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700">
            Body
          </label>
          <textarea
            name="body"
            className="mt-1 block w-full"
            rows={10}
            required
          ></textarea>
        </div>
        <button type="submit" className="btn btn-primary">
          Save
        </button>
      </Form>
      {actionData?.error && (
        <p className="text-red-500 mt-4">{actionData.error}</p>
      )}
    </div>
  );
}
