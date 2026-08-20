const { Client, GatewayIntentBits, Partials } = require("discord.js");
const axios = require("axios");

const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
const CHANNEL_ID = process.env.DISCORD_CHANNEL_ID || "1527074193823498283";
const MOVIE_TV_CHANNEL_ID = process.env.DISCORD_MOVIE_TV_CHANNEL_ID || "1527859066259374212";

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
});

client.on("messageCreate", async (message) => {
  // Ignore messages from the bot itself to prevent feedback loops
  if (message.author.id === client.user.id) return;
  // Ignore other bots
  if (message.author.bot) return;

  let targetWebhook = null;
  let channelType = "unknown";

  if (message.channelId === CHANNEL_ID) {
    targetWebhook = N8N_WEBHOOK_URL;
    channelType = "general-intake";
  } else if (message.channelId === MOVIE_TV_CHANNEL_ID) {
    targetWebhook = N8N_MOVIE_TV_WEBHOOK_URL;
    channelType = "movie-tv";
  } else {
    return;
  }

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
