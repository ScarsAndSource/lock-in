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
  morning: [
    'Good morning. Ek chhota kadam pehle, baaki din baad mein.',
    'Subah ho gayi. Bol, aaj kya karna hai?',
    'Uth gaya? Pehle paani, phir plan.',
  ],
  afternoon: [
    'Din aadha ho gaya. Bata, kaisa chal raha hai?',
    'Dopahar ho gayi. Kuch poochna hai apne logs ke baare mein?',
    'Lunch hua? Phir ek kaam nipta de.',
  ],
  evening: [
    'Shaam ho gayi. Aaj ka hisaab saath dekhein?',
    'Aaj ka din kaisa gaya? Logs se dekhte hain.',
    'Din dhal raha hai. Jo reh gaya, abhi bhi ho sakta hai.',
  ],
  night: [
    'Raat ho gayi. Aaj ka log kar de, phir aaram.',
    'Late ho raha hai. Jo poochna hai poochh, phir so ja.',
    'Screen band karne ka time ho raha hai, bhai.',
  ],
};

export const LISTENING: readonly string[] = ['Haan, bol.', 'Sun raha hoon.', 'Bol de, main yahin hoon.'];
export const THINKING: readonly string[] = [
  'Ruk, tere logs dekh raha hoon.',
  'Ek second, gada rakh ke hisaab laga raha hoon.',
  'Dekh raha hoon, sirf data se bolunga.',
  'Pannon ko palat raha hoon, ruk.',
];
export const REPLIED: readonly string[] = ['Ye raha.', 'Ye mila tere logs mein.'];
export const SUPPORT: readonly string[] = ['Main yahin hoon. Neeche di gayi madad ki lines dekh.'];
export const FAILED: readonly string[] = ['Kuch gadbad ho gayi. Ek baar phir bhej.', 'Network ne dhokha diya. Phir se try kar.'];
export const POKES: readonly string[] = [
  'Arre, gada lag jayegi.',
  'Haan haan, main yahin hoon.',
  'Gudgudi mat kar.',
  'Chal, ab kaam pe lag.',
  'Bol na, kya chahiye?',
  'Oye, cloud hil gaya.',
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
  'Kuch khaya? Khaali pet focus nahi hota.',
  'Baithe baithe jam jaoge, pair hila.',
];

/** While you type. */
export const PONDER: readonly string[] = [
  'Hmm…',
  'Achha, soch raha hoon…',
  'Haan, bol, sun raha hoon.',
  'Ruk, samajh raha hoon…',
  'Hmm, interesting.',
  'Aur bata…',
];
/** You stopped mid-message. */
export const NUDGES: readonly string[] = [
  'Bhej de na, soch mat.',
  'Adhura kyun chhod diya?',
  'Jo man mein hai, bol de.',
  'Main yahin hoon, jaldi nahi hai.',
];
export const WAKE: readonly string[] = [
  'Arre, jaag gaya main.',
  'Main so nahi raha tha. Bas aankh band thi.',
  'Aa gaya tu. Bol.',
  'Uff, neend aa gayi thi.',
];
export const AFTER_REPLY: readonly string[] = [
  'Kuch aur poochna hai?',
  'Samajh nahi aaya? Phir poochh.',
  'Ye tere logs se bola hai, andaza nahi.',
  'Ek step le, phir aana.',
  'Aur kuch? Main yahin hoon.',
];
/** On his own tab, waving at you. */
export const WAVES: readonly string[] = ['Oye! Idhar dekh.', 'Hello hello!', 'Namaste ji.', 'Kya haal?'];
export const IDLE_THOUGHTS: readonly string[] = [
  'Soch raha hoon, aaj tu kya karega…',
  'Kal ka din kaisa tha? Logs dekh lun?',
  'Hmm, sochne wali baat hai.',
  'Neend ka hisaab dekhein?',
];

/** When you switch tabs and he pops up above the tab you tapped. */
export const TAB_LINES = {
  now: [
    'Aaj ka hisaab yahin hai. Ek habit pakad.',
    'Now tab? Chal, jo pending hai woh nipta.',
    'Yahan se shuru kar, ek chhota kaam.',
    'Check-in kiya aaj?',
  ],
  mirror: [
    'Mirror… apna pattern khud dekh.',
    'Yahan jhooth nahi chalta. Data dikhata hai.',
    'Dekh, hafte mein kya chala aur kya nahi.',
    'Numbers se darr mat, bas seedha dekh.',
  ],
  crew: [
    'Crew! Dosto ke saath mazaa aata hai.',
    'Dekh kaun kya kar raha hai. Ranking nahi, bas saath.',
    'Kisi ko cheer bhej de, achha lagega.',
    'Crew Sunday ka card dekha?',
  ],
} as const satisfies Record<'now' | 'mirror' | 'crew', readonly string[]>;

/** Roaming on other tabs. */
export const PEEK_LINES: readonly string[] = [
  'Peek-a-boo!',
  'Main yahin hoon.',
  'Kaam ho raha hai? Dekh raha tha.',
  'Bas dekhne aaya tha.',
  'Hehe, pakda gaya.',
  'Chhup ke dekh raha hoon, kuch nahi.',
  'Paani piya?',
  'Ek habit aur, phir aaram.',
];
export const SIDE_LINES: readonly string[] = [
  'Idhar se jhaank raha hoon.',
  'Kya chal raha hai?',
  'Shh, kisi ko mat bolna.',
  'Tu kaam kar, main yahin hoon.',
];
export const FLY_LINES: readonly string[] = [
  'Udte hue bhi tujhpe nazar hai.',
  'Whoosh!',
  'Hawa mein ek chakkar.',
  'Upar se saaf dikhta hai, tu kar sakta hai.',
];
export const CLIMB_LINES: readonly string[] = [
  'Uffh, chadhai mushkil hai. Par ruk nahi sakta.',
  'Dekh, ek ek kadam. Habits bhi aise hi.',
  'Thoda saans le raha hoon.',
  'Upar tak jaana hai, tere saath.',
];
export const WALK_LINES: readonly string[] = [
  'Tehal raha hoon.',
  'Tera din kaisa ja raha hai?',
  'Tang mat ho, main kuch nahi kar raha.',
  'Ek kadam, phir ek kadam.',
];

export function pick<T>(items: readonly T[], avoid?: T): T {
  const pool = items.length > 1 && avoid !== undefined ? items.filter((i) => i !== avoid) : items;
  return pool[Math.floor(Math.random() * pool.length)];
}
