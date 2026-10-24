/** Maruti's wit and his reactions to what you type. Keyword-based and cheap; the backend still decides real support mode. */
export type Reaction = 'laugh' | 'greet' | 'thanks' | 'win' | 'tired' | 'bored' | 'angry' | 'sad' | 'crisis';

const RULES: [Reaction, RegExp][] = [
  ['crisis', /(suicid|kill myself|end my life|end it all|want to die|self[- ]?harm|marna chahta|marna chahti|jeena nahi|mar jaun|khud ko khatam)/i],
  ['sad', /\b(sad|depress\w*|lonely|hopeless|worthless|empty inside|crying|cried|miserable|heartbroken|anxious|hate myself|udaas|dukhi|akela|akeli|ro raha|ro rahi|bura lag\w*|toot gaya|haar gaya|feeling low|feeling down)\b/i],
  ['laugh', /(\b(?:ha){2,}h?\b|\bhehe+\b|\blol\b|\blmao\b|\brofl\b|😂|🤣|😆)/i],
  ['thanks', /\b(thanks?|thank you|thx|shukriya|dhanyavaad)\b/i],
  ['greet', /^\s*(hi+|hello+|hey+|yo+|namaste|sup|hola|oye)\b/i],
  ['win', /\b(did it|nailed it|aced it|crushed it|finally did|ho gaya|kar liya|pura ho gaya|completed|finished)\b/i],
  ['tired', /\b(tired|exhausted|sleepy|drained|burn(?:ed|t)? ?out|thak gaya|thak gayi|neend aa rahi)\b/i],
  ['bored', /\b(bored|boring|bore ho)\b/i],
  ['angry', /\b(angry|furious|pissed|annoyed|irritated|frustrated|gussa|chidh)\b/i],
];

export function classify(text: string): Reaction | null {
  const t = text.trim();
  if (!t) return null;
  const question = /\?\s*$/.test(t);
  for (const [kind, re] of RULES) {
    if (question && (kind === 'win' || kind === 'greet' || kind === 'thanks')) continue;
    if (re.test(t)) return kind;
  }
  return null;
}

export const LAUGH_BACK: readonly string[] = [
  'Hahaha! Ye toh mast tha.',
  'Oye, ab main hans hans ke gir jaunga!',
  'Haha, pet dukh gaya.',
  'Arre yaar, tu bhi na!',
  'Bas bas, cloud se gir jaunga!',
];
export const GREET_BACK: readonly string[] = [
  'Arre, aa gaya! Kaisa hai?',
  'Oye hoye! Bol bol.',
  'Namaste ji! Aaj kya scene hai?',
  'Aa, baith. Kya chal raha hai?',
];
export const THANKS_BACK: readonly string[] = [
  'Arre chhod, dost hai tu.',
  'Koi baat nahi. Ye kaam hi mera hai.',
  'Dil se. Ab aage badh.',
  'Mention not. Waise gada se zyaada tune kiya.',
];
export const WIN_BACK: readonly string[] = [
  'Wah! Ye hui na baat!',
  'Shabaash! Seedha taali.',
  'Dekha? Tu kar sakta hai.',
  'Ye toh gada se bhi bhaari kaam tha. Mast!',
];
export const TIRED_BACK: readonly string[] = [
  'Hmm, thaka lag raha hai. Thoda ruk, saans le.',
  'Aaj halka rakhte hain. Ek chhoti cheez, bas.',
  'Aaram bhi kaam ka hissa hai, bhai.',
];
export const BORED_BACK: readonly string[] = [
  'Bore? Chal, ek mazedaar sawaal poochh mujhse.',
  'Bore ho raha hai? Cloud pe baith, kuch sunata hoon.',
  'Bore hona achha hai, dimaag kuch naya sochta hai.',
];
export const ANGRY_BACK: readonly string[] = [
  'Theek hai, bol. Main sun raha hoon, bina bole.',
  'Gussa jaayaz hai. Pehle ek lamba saans, phir bata.',
  'Main yahin hoon. Jo dil mein hai nikal de.',
];
export const SAD_BACK: readonly string[] = [
  'Main yahin hoon. Aur dekh, main bada bhi ho gaya. Tu akela nahi hai.',
  'Sun, ye bhaari lag raha hai, par hum dono saath hain. Saath mein hum bhaari pad jaate hain.',
  'Main yahin khada hoon, tere saath. Jitna bada chahiye, utna ban jaunga.',
];
/** While he stands guard next to you. Steady, never jokey. */
export const GUARD_LINES: readonly string[] = [
  'Main yahin hoon.',
  'Hum dono saath mein, kuch bhi jhel lenge.',
  'Saans le. Dheere dheere.',
  'Tu akela nahi hai. Main khada hoon.',
  'Ek kadam. Bas ek.',
  'Bol jab bolna ho. Jaldi nahi hai.',
];
export const COMFORT_END: readonly string[] = [
  'Theek hai, main side mein hoon. Zarurat ho toh bata.',
  'Chhota ho gaya, par yahin hoon.',
];
/** While you type and he is leaning in on your input box. */
export const EAVES: readonly string[] = [
  'Main kuch nahi sun raha. Bas padh raha hoon.',
  'Shhh… likh, likh.',
  'Dekh raha hoon kya likh raha hai, hehe.',
  'Kaan lagaye baitha hoon.',
  'Hmm hmm… aage bol.',
];
/** Roll-on-the-floor lines. */
export const SELF_LAUGH: readonly string[] = [
  'Hahaha, ruk ruk, pet dukh gaya!',
  'Main hans ke lot-pot ho gaya!',
  'Haha, kisi ne dekha toh nahi?',
];
/** His own jokes, told on his own tab. He laughs at them himself. */
export const JOKES: readonly string[] = [
  'Lanka jala di thi maine. Tu ek habit shuru nahi kar sakta? Chal na.',
  'Mera cloud 5G nahi, seedha upar se signal deta hai. Hehe.',
  'Tune kal bola tha "kal se pakka". Dekh, kal aaj ban gaya.',
  'Meri gada 100 kilo ki hai. Tera "bas 5 minute" usse bhaari hai.',
  'Maine pahaad uthaya tha. Tu ek glass paani nahi utha raha?',
  'Sab kehte hain bandar ki naqal. Main toh original hoon, copy nahi.',
  'Cloud pe baitha hoon, isliye mera mood hamesha partly cloudy hai.',
  'Hisaab? Mujhe toh bas tera aaj chahiye. Kal ki chinta kal.',
];
