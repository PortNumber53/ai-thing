import { MetaFunction } from "@remix-run/node";

export const meta: MetaFunction = () => {
  return [
    { title: "Mauricio's Blog" },
    { name: "description", content: "Personal blog exploring technology, design, and creativity" }
  ];
};

export default function Index() {
  return (
    <div className="bg-white min-h-screen">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <header className="border-b-2 border-gray-100 pb-8 mb-12">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-gray-900">Mauricio Otta</h1>
            <nav>
              <ul className="flex space-x-4">
                <li><a href="#" className="text-gray-600 hover:text-gray-900 transition-colors">Blog</a></li>
                <li><a href="#" className="text-gray-600 hover:text-gray-900 transition-colors">About</a></li>
                <li><a href="#" className="text-gray-600 hover:text-gray-900 transition-colors">Projects</a></li>
              </ul>
            </nav>
          </div>
          <p className="mt-4 text-lg text-gray-600">
            Software Engineer | Design Enthusiast | AI Explorer
          </p>
        </header>

        <main>
          <section className="mb-16">
            <h2 className="text-2xl font-bold text-gray-900 mb-6">Latest Posts</h2>
            
            <article className="mb-12 pb-12 border-b border-gray-100">
              <div className="flex items-center mb-4">
                <span className="text-sm text-gray-500 mr-4">January 18, 2025</span>
                <span className="px-2 py-1 bg-blue-50 text-blue-800 text-xs rounded-full">Technology</span>
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-3 hover:text-blue-600 transition-colors">
                <a href="#">Exploring the Intersection of AI and Design</a>
              </h3>
              <p className="text-gray-600 mb-4">
                Dive into how artificial intelligence is reshaping the landscape of design, 
                from user experience to creative processes.
              </p>
              <a href="#" className="text-blue-600 hover:underline">Read more →</a>
            </article>

            <article className="mb-12 pb-12 border-b border-gray-100">
              <div className="flex items-center mb-4">
                <span className="text-sm text-gray-500 mr-4">December 25, 2024</span>
                <span className="px-2 py-1 bg-green-50 text-green-800 text-xs rounded-full">Web Development</span>
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-3 hover:text-blue-600 transition-colors">
                <a href="#">Building Modern Web Applications with Remix</a>
              </h3>
              <p className="text-gray-600 mb-4">
                A deep dive into Remix's innovative approach to web development, 
                exploring its performance benefits and developer experience.
              </p>
              <a href="#" className="text-blue-600 hover:underline">Read more →</a>
            </article>

            <article className="mb-12">
              <div className="flex items-center mb-4">
                <span className="text-sm text-gray-500 mr-4">November 10, 2024</span>
                <span className="px-2 py-1 bg-purple-50 text-purple-800 text-xs rounded-full">Personal Growth</span>
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-3 hover:text-blue-600 transition-colors">
                <a href="#">My Journey in Tech: Lessons Learned</a>
              </h3>
              <p className="text-gray-600 mb-4">
                Reflecting on key moments and insights gained throughout my 
                career in software engineering and design.
              </p>
              <a href="#" className="text-blue-600 hover:underline">Read more →</a>
            </article>
          </section>

          <section className="bg-gray-50 p-8 rounded-lg">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">About Me</h2>
            <div className="flex items-center">
              <div className="w-24 h-24 rounded-full bg-gray-200 mr-6 overflow-hidden">
                {/* Placeholder for profile image */}
                <div className="w-full h-full flex items-center justify-center text-gray-500">
                  Photo
                </div>
              </div>
              <div>
                <p className="text-gray-600">
                  I'm a software engineer passionate about creating innovative solutions 
                  at the intersection of technology, design, and user experience. 
                  Currently exploring the potential of AI and web technologies.
                </p>
              </div>
            </div>
          </section>
        </main>

        <footer className="mt-16 pt-8 border-t border-gray-100 text-center">
          <p className="text-gray-600">
            &copy; 2025 Mauricio Otta. All rights reserved.
          </p>
          <div className="mt-4 flex justify-center space-x-4">
            <a href="#" className="text-gray-500 hover:text-gray-900">GitHub</a>
            <a href="#" className="text-gray-500 hover:text-gray-900">LinkedIn</a>
            <a href="#" className="text-gray-500 hover:text-gray-900">Twitter</a>
          </div>
        </footer>
      </div>
    </div>
  );
}
