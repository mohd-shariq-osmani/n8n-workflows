const { Client, GatewayIntentBits, Partials } = require("discord.js");
const axios = require("axios");

const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
const CHANNEL_ID = process.env.DISCORD_CHANNEL_ID || "1527074193823498283";
const MOVIE_TV_CHANNEL_ID = process.env.DISCORD_MOVIE_TV_CHANNEL_ID || "1527859066259374212";
const ANIME_CHANNEL_ID = process.env.DISCORD_ANIME_CHANNEL_ID || "1538893352668233789";

const N8N_WEBHOOK_URL = process.env.N8N_WEBHOOK_URL || "http://n8n:5678/webhook/discord-intake";
const N8N_MOVIE_TV_WEBHOOK_URL = process.env.N8N_MOVIE_TV_WEBHOOK_URL || "http://n8n:5678/webhook/movie-tv";

if (!BOT_TOKEN) {
  console.error("Missing required DISCORD_BOT_TOKEN environment variable.");
  process.exit(1);
}

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
  partials: [Partials.Message, Partials.Channel],
});

client.once("ready", () => {
  console.log(`Logged in as ${client.user.tag}`);
  console.log(`Watching General intake channel: ${CHANNEL_ID} -> ${N8N_WEBHOOK_URL}`);
  console.log(`Watching Movie/TV channel: ${MOVIE_TV_CHANNEL_ID} -> ${N8N_MOVIE_TV_WEBHOOK_URL}`);
  console.log(`Watching Anime channel: ${ANIME_CHANNEL_ID} -> ${N8N_MOVIE_TV_WEBHOOK_URL}`);
});

client.on("messageCreate", async (message) => {
  const content = message.content || "";
  const isMovieChannel = message.channelId === MOVIE_TV_CHANNEL_ID;
  const isAnimeChannel = message.channelId === ANIME_CHANNEL_ID;
  const isGeneralChannel = message.channelId === CHANNEL_ID;

  if (!isMovieChannel && !isAnimeChannel && !isGeneralChannel) {
    return;
  }

  // Prevent feedback loop: ignore confirmation/error cards from the Media Dispatcher
  if (
    content.includes("Radarr Download Queued") ||
    content.includes("Sonarr Download Queued") ||
    content.includes("Library Check") ||
    content.includes("IMDb Media Router Error") ||
    content.includes("Workflow Error Alert") ||
    content.includes("already in your **Radarr** library") ||
    content.includes("already in your **Sonarr** library")
  ) {
    return;
  }

  let targetWebhook = null;
  let channelType = "unknown";

  if (isGeneralChannel) {
    // Only forward human user messages from general intake
    if (message.author.bot || message.author.id === client.user.id) return;
    targetWebhook = N8N_WEBHOOK_URL;
    channelType = "general-intake";
  } else if (isMovieChannel || isAnimeChannel) {
    channelType = isMovieChannel ? "movie-tv" : "anime-manhua";
    // If sent by bot, only forward if it contains an IMDb link or ttID
    if (message.author.bot || message.author.id === client.user.id) {
      const hasImdb = /imdb\.com\/title\/tt\d+|tt\d{7,8}/i.test(content);
      if (!hasImdb) {
        return;
      }
    }
    targetWebhook = N8N_MOVIE_TV_WEBHOOK_URL;
  }

  if (!targetWebhook) return;

  const payload = {
    messageId: message.id,
    channelId: message.channelId,
    channelType: channelType,
    authorId: message.author.id,
    authorUsername: message.author.username,
    content: message.content,
    attachments: message.attachments.map((a) => ({
      url: a.url,
      name: a.name,
      contentType: a.contentType,
    })),
    timestamp: message.createdAt.toISOString(),
  };

  try {
    await axios.post(targetWebhook, payload, {
      headers: { "Content-Type": "application/json" },
      timeout: 15000,
    });
    console.log(`Forwarded message ${message.id} from #${channelType} to ${targetWebhook}`);
  } catch (err) {
    console.error(
      `Failed to forward message ${message.id} to ${targetWebhook}:`,
      err.response?.status,
      err.message
    );
  }
});

client.login(BOT_TOKEN);

