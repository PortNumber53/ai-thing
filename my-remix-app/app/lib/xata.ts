import { XataClient } from "../../vendor/xata";

// Shared Xata client initialization for both server and client
export const getXataClient = () => {
  // Only allow server-side initialization
  if (typeof window === "undefined") {
    const xataApiKey = process.env.XATA_API_KEY;
    const xataDatabaseURL = process.env.XATA_DATABASE_URL;
    const xataBranch = process.env.XATA_BRANCH || "main";

    if (xataApiKey && xataDatabaseURL) {
      return new XataClient({
        apiKey: xataApiKey,
        databaseURL: xataDatabaseURL,
        branch: xataBranch,
      });
    }

    throw new Error(
      "Xata client initialization failed: Missing API key or database URL"
    );
  }
};

// Keep the existing xata export for backwards compatibility
export const xata = getXataClient();

// Helper function to get content by url_path
export async function getContent(url_path: string): Promise<any | null> {
  try {
    console.log("XATA Fetching content for url_path:", url_path);
    const record = await xata.db.contents.filter({ url_path }).getFirst();
    console.log("Fetched record:", record);

    return record || null;
  } catch (error) {
    console.error("Error fetching content:", error);
    return null;
  }
}

// Helper function to get multiple contents
export async function getAllContents(): Promise<string[]> {
  try {
    const records = await xata.db.contents.getMany();

    return records
      .map((record) => record.content?.current as string)
      .filter((content) => content !== undefined);
  } catch (error) {
    console.error("Error fetching contents:", error);
    return [];
  }
}

// Helper function to save or update content
export async function saveContent(
  url_path: string,
  payload: { title?: string; body?: string }
) {
  // Validate input
  if (!url_path) {
    throw new Error("Content url_path is required");
  }

  if (payload === undefined || payload === null) {
    throw new Error("Content cannot be undefined or null");
  }

  console.log("Saving content:", { url_path, payload });

  try {
    // Attempt to find existing record
    const existingRecord = await xata.db.contents
      .filter({ url_path })
      .getFirst();

    console.log("existingRecord:", { existingRecord });

    // Prepare content to save
    const contentToSave = {
      url_path,
      title: payload.title,
      content: { current: payload.body },
    };

    let savedRecord;
    if (existingRecord) {
      // Update existing record
      savedRecord = await xata.db.contents.update(
        existingRecord.xata_id,
        contentToSave
      );
    } else {
      // Create new record
      savedRecord = await xata.db.contents.create(contentToSave);
    }

    // Log saved record for verification
    console.log("Saved record:", savedRecord);

    return savedRecord;
  } catch (error) {
    // Enhanced error logging
    console.error("Detailed error saving content:", {
      url_path,
      payload,
      errorMessage: error instanceof Error ? error.message : "Unknown error",
      errorStack: error instanceof Error ? error.stack : "No stack trace",
    });

    // Rethrow the error to be handled by the caller
    throw error;
  }
}
