import { Form, useActionData, useLoaderData, useNavigation } from "@remix-run/react";
import { ActionFunctionArgs, json, redirect } from "@remix-run/node";
import { getContent, saveContent } from "~/lib/xata";
import { useState, useEffect } from "react";
import ReactMarkdown from 'react-markdown';

// Themes for markdown preview
const themes = {
  default: 'prose prose-gray',
  dark: 'prose prose-invert',
  colorful: 'prose prose-blue'
};

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

    return json({ 
      success: true,
      message: 'Content saved successfully'
    });
  } catch (error) {
    console.error('Unexpected error in edit route:', error);

    return json({
      success: false,
      errors: {
        general: error instanceof Error
          ? `Failed to save content: ${error.message}`
          : 'An unexpected error occurred while saving content'
      }
    }, { status: 500 });
  }
}

export default function EditPage() {
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const loaderData = useLoaderData<typeof loader>();

  // State for markdown content
  const [markdownContent, setMarkdownContent] = useState(
    actionData?.homeContent?.body || 
    loaderData?.homeContent?.content?.current || 
    ''
  );

  // State for markdown title
  const [markdownTitle, setMarkdownTitle] = useState(
    actionData?.homeContent?.title || 
    loaderData?.homeContent?.title || 
    ''
  );

  // State for save success message
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // Effect to handle save success message
  useEffect(() => {
    if (actionData?.success) {
      setSaveMessage(actionData.message || 'Content saved successfully');
      const timer = setTimeout(() => setSaveMessage(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [actionData]);

  // Handle markdown content change
  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMarkdownContent(e.target.value);
  };

  // Handle markdown title change
  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMarkdownTitle(e.target.value);
  };

  return (
    <Form method="post" className="h-screen flex flex-col">
      {/* Header */}
      <header className="bg-gray-100 border-b p-4 flex justify-between items-center">
        <h1 className="text-xl font-semibold">Markdown Editor</h1>
        <div className="space-x-2 flex items-center">
          {saveMessage && (
            <span className="text-green-600 mr-4">{saveMessage}</span>
          )}
          <button 
            type="submit"
            disabled={navigation.state === 'submitting'}
            className={`px-4 py-2 rounded text-white transition-all duration-200 ${
              navigation.state === 'submitting'
                ? 'bg-blue-500 cursor-wait'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {navigation.state === 'submitting' ? 'Saving...' : 'Save'}
          </button>
        </div>
      </header>

      {/* Two-Column Layout */}
      <div className="flex flex-grow overflow-hidden">
        {/* Left Column: Markdown Input */}
        <div className="w-1/2 border-r p-4 flex flex-col">
          <input 
            type="text"
            name="title"
            placeholder="Enter title"
            value={markdownTitle}
            onChange={handleTitleChange}
            className="w-full p-2 mb-4 border rounded text-xl font-bold"
          />
          <textarea 
            name="body"
            placeholder="Write your markdown here..."
            value={markdownContent}
            onChange={handleContentChange}
            className="flex-grow w-full p-2 border rounded resize-none"
          />
        </div>

        {/* Right Column: Markdown Preview */}
        <div className="w-1/2 p-4 bg-gray-50 overflow-auto prose max-w-none">
          <h1>{markdownTitle}</h1>
          <ReactMarkdown>{markdownContent}</ReactMarkdown>
        </div>
      </div>
    </Form>
  );
}
