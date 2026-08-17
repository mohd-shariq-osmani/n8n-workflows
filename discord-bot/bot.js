const { Client, GatewayIntentBits, Partials } = require("discord.js");
const axios = require("axios");

const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
const CHANNEL_ID = process.env.DISCORD_CHANNEL_ID;
const N8N_WEBHOOK_URL = process.env.N8N_WEBHOOK_URL;

if (!BOT_TOKEN || !CHANNEL_ID || !N8N_WEBHOOK_URL) {
  console.error(
    "Missing required env vars. Need DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, N8N_WEBHOOK_URL."
  );
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
  console.log(`Watching channel ID: ${CHANNEL_ID}`);
  console.log(`Forwarding to: ${N8N_WEBHOOK_URL}`);
});

client.on("messageCreate", async (message) => {
  // Ignore messages from bots (including itself) to avoid loops
  if (message.author.bot) return;

  // Only forward messages from the configured intake channel
  if (message.channelId !== CHANNEL_ID) return;

  const payload = {
    messageId: message.id,
    channelId: message.channelId,
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
    await axios.post(N8N_WEBHOOK_URL, payload, {
      headers: { "Content-Type": "application/json" },
      timeout: 10000,
    });
    console.log(`Forwarded message ${message.id} to n8n`);
  } catch (err) {
    console.error(
      `Failed to forward message ${message.id}:`,
      err.response?.status,
      err.message
    );
  }
});

client.login(BOT_TOKEN);
