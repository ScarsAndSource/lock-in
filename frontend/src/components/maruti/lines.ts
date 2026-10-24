/** Everything Maruti says on his own. Edit freely: short, warm, direct. The data answers still come from the analyst. */
export type DayPart = 'morning' | 'afternoon' | 'evening' | 'night';

export function dayPart(d: Date): DayPart {
  const h = d.getHours();
  if (h >= 5 && h < 12) return 'morning';
  if (h >= 12 && h < 17) return 'afternoon';
  if (h >= 17 && h < 22) return 'evening';
  return 'night';
}

export const GREETINGS: Record<DayPart, readonly string[]> = {
  morning: ['Good morning. Ek chhota kadam pehle, baaki din baad mein.', 'Subah ho gayi. Bol, aaj kya karna hai?'],
  afternoon: ['Din aadha ho gaya. Bata, kaisa chal raha hai?', 'Dopahar ho gayi. Kuch poochna hai apne logs ke baare mein?'],
  evening: ['Shaam ho gayi. Aaj ka hisaab saath dekhein?', 'Aaj ka din kaisa gaya? Logs se dekhte hain.'],
  night: ['Raat ho gayi. Aaj ka log kar de, phir aaram.', 'Late ho raha hai. Jo poochna hai poochh, phir so ja.'],
};

export const LISTENING: readonly string[] = ['Haan, bol.', 'Sun raha hoon.', 'Bol de, main yahin hoon.'];
export const THINKING: readonly string[] = [
  'Ruk, tere logs dekh raha hoon.',
  'Ek second, gada rakh ke hisaab laga raha hoon.',
  'Dekh raha hoon, sirf data se bolunga.',
];
export const REPLIED: readonly string[] = ['Ye raha.', 'Ye mila tere logs mein.'];
export const SUPPORT: readonly string[] = ['Main yahin hoon. Neeche di gayi madad ki lines dekh.'];
export const FAILED: readonly string[] = ['Kuch gadbad ho gayi. Ek baar phir bhej.'];
export const POKES: readonly string[] = [
  'Arre, gada lag jayegi.',
  'Haan haan, main yahin hoon.',
  'Gudgudi mat kar.',
  'Chal, ab kaam pe lag.',
  'Bol na, kya chahiye?',
];
export const POKES_MANY: readonly string[] = [
  'Bas bas. Itna toh Sanjeevani laane mein bhi time nahi laga tha.',
  'Ab bahut ho gaya. Ek habit log kar, phir aana.',
];
export const IDLE_CHATTER: readonly string[] = [
  'Paani piya?',
  'Ek lamba saans le.',
  'Screen se nazar hata, bees second.',
  'Kandhe dheele kar.',
  'Aaj ka ek kaam, bas ek.',
];

export function pick<T>(items: readonly T[], avoid?: T): T {
  const pool = items.length > 1 && avoid !== undefined ? items.filter((i) => i !== avoid) : items;
  return pool[Math.floor(Math.random() * pool.length)];
}
