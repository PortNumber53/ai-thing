import { MetaFunction, LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData, Link } from "@remix-run/react";
import { getAllContents } from "~/lib/xata";
import { json } from "@remix-run/node";

export const meta: MetaFunction = () => {
  return [
    { title: "Blog Dashboard" },
    {
      name: "description",
      content: "Manage blog entries",
    },
  ];
};

export async function loader({ request }: LoaderFunctionArgs) {
  const contents = await getAllContents();
  return json(contents);
}

export default function BlogDashboard() {
  const contents = useLoaderData<typeof loader>();

  return (
    <div className="container mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-4">Blog Dashboard</h1>
      <Link to="/dashboard/blog/new" className="btn btn-primary mb-4">
        Create New Blog Entry
      </Link>
      <ul>
        {contents.map((content, index) => (
          <li key={index} className="mb-2">
            <Link
              to={`/dashboard/blog/edit/${content.url_path}`}
              className="text-blue-500"
            >
              {content.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
