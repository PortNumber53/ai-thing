import { Form, useActionData, useLoaderData, useNavigation } from "@remix-run/react";
import { ActionFunctionArgs, json, redirect } from "@remix-run/node";
import { getContent, saveContent } from "~/lib/xata";

// Validation function for content
function validateContent(content: { title: string; body: string }) {
  const errors: { title?: string; body?: string } = {};

  if (!content.title || content.title.trim() === '') {
    errors.title = 'Title is required';
  }

  if (!content.body || content.body.trim() === '') {
    errors.body = 'Body content is required';
  }

  return Object.keys(errors).length > 0 ? errors : null;
}

export async function loader() {
  const homeContent = await getContent('homepage');
  return json({ homeContent });
}

export async function action({ request }: ActionFunctionArgs) {
  try {
    const formData = await request.formData();

    // Parse form data
    const homeContent = {
      title: formData.get('title')?.toString() || '',
      body: formData.get('body')?.toString() || ''
    };

    // Validate content
    const validationErrors = validateContent(homeContent);
    if (validationErrors) {
      return json({
        errors: validationErrors,
        homeContent
      }, { status: 400 });
    }

    // Save content
    await saveContent('homepage', homeContent);

    return redirect('/');
  } catch (error) {
    console.error('Unexpected error in edit route:', error);

    // More detailed error handling
    return json({
      errors: {
        general: error instanceof Error
          ? `Failed to save content: ${error.message}`
          : 'An unexpected error occurred while saving content'
      },
      homeContent: null
    }, { status: 500 });
  }
}

export default function EditPage() {
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const loaderData = useLoaderData<typeof loader>();

  // Prioritize actionData, fallback to loaderData
  const { homeContent } = actionData || loaderData || {};
  const errors = actionData?.errors || {};

  return (
    <div className="h-screen bg-gray-100 flex flex-col antialiased">
      {/* Window Header */}
      <div className="bg-gray-200 border-b border-gray-300 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-3 h-3 bg-red-500 rounded-full"></div>
          <div className="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <div className="w-3 h-3 bg-green-500 rounded-full"></div>
        </div>
        <h2 className="text-sm font-medium text-gray-600">
          Edit Homepage Content
        </h2>
        <div className="w-12"></div>
      </div>

      {/* Toolbar */}
      <div className="bg-gray-50 border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button className="text-gray-600 hover:bg-gray-200 p-2 rounded transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>
          <button className="text-gray-600 hover:bg-gray-200 p-2 rounded transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </button>
        </div>
        <div className="text-xs text-gray-500">
          Last saved: {new Date().toLocaleString()}
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-grow overflow-auto p-8">
        <div className="max-w-4xl mx-auto bg-white shadow-lg rounded-lg p-8 space-y-6">
          {/* Error Handling */}
          {errors.general && (
            <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg flex items-center">
              <svg className="h-5 w-5 text-red-400 mr-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <p className="text-sm">{errors.general}</p>
            </div>
          )}

          {/* Edit Form */}
          <Form method="post" className="space-y-6">
            {/* Title Input */}
            <div>
              <label 
                htmlFor="title" 
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Page Title
              </label>
              <input
                id="title"
                type="text"
                name="title"
                defaultValue={homeContent?.title}
                placeholder="Enter your page title"
                className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
                  errors.title 
                    ? 'border-red-300 focus:ring-red-500' 
                    : 'border-gray-300 focus:ring-blue-500'
                } transition-all duration-200`}
              />
              {errors.title && (
                <p className="mt-2 text-sm text-red-600">{errors.title}</p>
              )}
            </div>

            {/* Body Input */}
            <div>
              <label 
                htmlFor="body" 
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Page Content
              </label>
              <textarea
                id="body"
                name="body"
                rows={10}
                defaultValue={homeContent?.content?.current}
                placeholder="Write your page content here..."
                className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
                  errors.body 
                    ? 'border-red-300 focus:ring-red-500' 
                    : 'border-gray-300 focus:ring-blue-500'
                } transition-all duration-200`}
              />
              {errors.body && (
                <p className="mt-2 text-sm text-red-600">{errors.body}</p>
              )}
            </div>

            {/* Submit Button */}
            <div className="flex justify-end space-x-4">
              <button
                type="button"
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={navigation.state === 'submitting'}
                className={`px-6 py-2 rounded-md text-white transition-all duration-200 ${
                  navigation.state === 'submitting'
                    ? 'bg-blue-500 cursor-wait'
                    : 'bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500'
                }`}
              >
                {navigation.state === 'submitting' ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </Form>
        </div>
      </div>
    </div>
  );
}
