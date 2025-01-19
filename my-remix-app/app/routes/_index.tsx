import { MetaFunction, LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import { getContent } from "~/lib/xata";
import { json } from "@remix-run/node";
import ReactMarkdown from 'react-markdown';

export const meta: MetaFunction = () => {
  return [
    { title: "Mauricio's Blog" },
    { name: "description", content: "Personal blog exploring technology, design, and creativity" }
  ];
};

export async function loader({ request }: LoaderFunctionArgs) {
  const payloadContent = await getContent('homepage');
  return json({ payloadContent });
}

export default function Index() {
  const { payloadContent } = useLoaderData<typeof loader>();

  // GNOME-inspired color palette
  const colors = {
    background: 'bg-[#f6f5f4]',
    primary: 'bg-[#3584e4]',
    text: {
      primary: 'text-[#2a2a2a]',
      secondary: 'text-[#5c5c5c]'
    },
    accent: 'bg-[#4a90d9]'
  };

  return (
    <div className={`min-h-screen ${colors.background} flex flex-col antialiased`}>
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-8 w-8 text-[#3584e4]"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/>
            </svg>
            <span className="text-[#2a2a2a]">Maurício Otta</span>
          </div>
          <h1 className={`text-xl font-medium ${colors.text.primary} absolute left-1/2 transform -translate-x-1/2`}>
            {payloadContent?.title}
          </h1>
          <nav>
            <ul className="flex space-x-4">
              {/* Edit button removed */}
            </ul>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-12 flex-grow">
        <div className="max-w-3xl mx-auto">

          {/* Content Section */}
          <section
            className={`bg-white rounded-lg shadow-md p-8 ${colors.text.primary} prose prose-lg`}
          >
            <div>
              <ReactMarkdown>
                {payloadContent?.content?.current}
              </ReactMarkdown>
            </div>
          </section>

          {/* Social Links */}
          <section className="mt-12 text-center">
            <div className="flex justify-center space-x-6">
              {[
                {
                  name: 'GitHub',
                  icon: (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-6 w-6"
                      fill="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <title>GitHub profile for Mauricio Otta</title>
                      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                    </svg>
                  ),
                  href: 'https://github.com/mauriciootta'
                },
                {
                  name: 'LinkedIn',
                  icon: (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-6 w-6"
                      fill="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <title>LinkedIn profile for Mauricio Otta</title>
                      <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.784 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
                    </svg>
                  ),
                  href: 'https://linkedin.com/in/mauriciootta'
                },
                {
                  name: 'Twitter',
                  icon: (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-6 w-6"
                      fill="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <title>Twitter profile for Mauricio Otta</title>
                      <path d="M24 4.557c-.883.392-1.832.656-2.828.775 1.017-.609 1.798-1.574 2.165-2.724-.951.564-2.005.974-3.127 1.195-.897-.957-2.178-1.555-3.594-1.555-3.179 0-5.515 2.966-4.797 6.045-4.091-.205-7.719-2.165-10.148-5.144-1.29 2.213-.669 5.108 1.523 6.574-.806-.026-1.566-.247-2.229-.616-.054 2.281 1.581 4.415 3.949 4.89-.693.188-1.452.232-2.224.084.626 1.956 2.444 3.379 4.6 3.419-2.07 1.623-4.678 2.348-7.29 2.04 2.179 1.397 4.768 2.212 7.548 2.212 9.142 0 14.307-7.721 13.995-14.646.962-.695 1.797-1.562 2.457-2.549z"/>
                    </svg>
                  ),
                  href: 'https://twitter.com/mauriciootta'
                }
              ].map((social) => (
                <a
                  key={social.name}
                  href={social.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`text-gray-500 hover:${colors.primary} transition-colors`}
                  aria-label={social.name}
                >
                  {social.icon}
                </a>
              ))}
            </div>
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 py-6">
        <div className="container mx-auto px-4 text-center">
          <p className={`text-sm ${colors.text.secondary}`}>
            &copy; 2025 Mauricio S. Otta. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
