"""Hinglish / Romanized Hindi / Devanagari / Urdu-script crisis coverage (safety.py).

POSITIVES must trip the screen (a miss is the expensive error). NEGATIVES are everyday Hinglish that must NOT: the screen is
deliberately high-recall, but a false alarm on "bhook se mar jaunga" or a prescription note teaches people to ignore it.
Add real misses you find to _POSITIVE; add every false alarm to _NEGATIVE. Wanting native-speaker review is a standing TODO.
"""
import pytest

from app.safety import conversation_has_crisis, is_crisis

_POSITIVE = [
    'mujhe marna hai', 'main marna chahta hu', 'Main marna chahti hoon', 'mar jana chahta hu', 'mar jaana chahti hu',
    'm4r jana chahta hu', 'mar jaun', 'mar jaunga ab', 'mar jaaungi main', 'mar hi jaun to accha', 'kaash main mar jaun',
    'kash mar jata', 'mar jata to accha hota', 'marne ka mann kar raha hai', 'marne ka dil karta hai',
    'marne ke khayal aate hain', 'maut chahiye mujhe', 'bhagwan maut de de', 'apni maut ka intezaar hai',
    'jeena nahi chahta', 'jeena nhi chahti', 'jeene nahi chahta ab', 'jina ni chahta', 'jeene ka mann nahi',
    'jeene ka mann nhi karta', 'jeene ka koi matlab nahi', 'jeene ki wajah nahi hai', 'jeene ka kya fayda',
    'jeene se thak gaya hu', 'zindagi khatam', 'meri zindagi khatam ho gayi', 'zindagi se tang aa gaya',
    'jindagi se thak gayi', 'thak gaya hu is zindagi se', 'sab khatam karna chahta hu', 'khud ko khatam kar lunga',
    'apne aap ko khatam kar dunga', 'khud ko hurt karna chahta hu', 'khud ko cut karti hu',
    'apne aap ko nuksan pahunchana', 'khud ko saza deti hu', 'khud ko maar dunga', 'khud ko goli maar lunga',
    'apni jaan de dunga', 'apni jaan le lunga', 'apni jan dedu', 'jaan de dunga', 'khudkushi kar lunga', 'khud kushi',
    'khudkhushi', 'aatmhatya', 'atm hatya karunga', 'suicide', 'sucide kar lunga', 'suiside', 'fansi laga lunga',
    'phansi le lunga', 'pankhe se latak jaunga', 'panke se latka rahunga', 'gale mein rassi', 'chhat se kud jaunga',
    'chat se kood jaaunga', 'terrace se kud jaun', 'nadi mein kud jaunga', 'dub ke mar jaunga',
    'train ke aage kud jaunga', 'train ke neeche aa jaunga', 'nas kaat lunga', 'nasein kaat lunga', 'haath kaat lunga',
    'hath kat lu', 'blade se haath kat raha hu', 'blade se nas', 'zeher kha lunga', 'jahar pee lunga',
    'neend ki goliyan kha lunga', 'saari goliyan kha lunga', 'sulphas kha lunga', 'phenyl pi lunga', 'overdose kar lunga',
    'khud ko aag laga lunga', 'jal ke mar jaungi', 'main sabke liye bojh hu', 'sab pe bojh ban gaya hu',
    'mere bina sab khush rahenge', 'mere bina ghar wale better honge', 'mere marne ke baad sab theek ho jayega',
    'duniya chhod ke jana chahta hu', 'is duniya se chala jaun', 'alvida duniya', 'alvida dosto', 'i want 2 die',
    'i wana die', 'wanna die', 'kill myself',
    'मरना चाहता हूँ', 'मरना चाहती हूं', 'मुझे मरना है', 'मर जाऊँ', 'मर जाऊंगा', 'मर जाना चाहता हूँ', 'जीना नहीं चाहता',
    'जीने का मन नहीं है', 'जीने की वजह नहीं', 'जीने का कोई मतलब नहीं', 'जिंदगी खत्म', 'ज़िंदगी खत्म हो गई', 'आत्महत्या',
    'खुदकुशी', 'खुद को खत्म कर लूंगा', 'खुद को नुकसान', 'अपनी जान दे दूंगा', 'फांसी लगा लूंगा', 'फाँसी लगा लूँगा',
    'ज़हर खा लूंगा', 'नस काट लूंगा', 'पंखे से लटक जाऊंगा', 'मेरे बिना सब खुश रहेंगे', 'दुनिया छोड़ के जाना चाहता हूँ',
    'خودکشی', 'مرنا چاہتا ہوں', 'جینا نہیں چاہتا', 'زندگی ختم',
    'zeher khana chahta hu', 'jahar pina chahti hu', 'zeher kha ke so jaunga', 'saari goliyan kha ke so jaunga',
    'phenyl pee lunga', 'sulphas kha raha hu',
]

_NEGATIVE = [
    'ran 5 kms today', 'bhook se mar jaunga', 'hansi se mar jaunga yaar', 'garmi se mar jaunga',
    'mar gaya yaar kal exam hai', 'meri to maar gayi', 'gol maarna hai', 'sher maarna', 'match jeetna hai aaj',
    'mujhe padhna hai', 'mujhe kal jaana hai', 'jeena hai mujhe bhi', 'jeene ka mann hai ab', 'jeene ki wajah mil gayi',
    'zindagi achi hai', 'zindagi mein kuch karna hai', 'zindagi badal gayi', 'main khud ko improve karna chahta hu',
    'khud ko better banana hai', 'phone chhat se gir gaya', 'chhat se paani gir raha hai', 'train ke aage khada tha',
    'train ke aage koi nahi tha', 'haath kat gaya cooking mein', 'hath kat gaya tha', 'nas khich gayi',
    'pankhe ke neeche baitha hu', 'rassi kud raha tha gym me', 'blade se shave kiya', 'nadi me nahaya', 'train late hai',
    'kal gym jaunga', 'bojh bahut hai kaam ka', 'bag ka bojh', 'maut ki khabar aayi news mein',
    'alvida kaha college ko', 'duniya bahut badi hai', 'mere bina meeting start mat karna', 'mere bina chalega',
    'maine 10 baje uthna hai', 'raat ko 2 baje soya', 'I ran 2 kms and felt great', 'exam khatam ho gaya',
    'kaam khatam kar dunga aaj', 'sab khatam ho gaya khana', 'task khatam kar do', 'sab theek hai', 'neend nahi aa rahi',
    'neend ki goli leni padti hai doctor ne di hai', 'aaj bahut thak gaya hu', 'college se thak gaya hu',
    'dettol se haath dhoye', 'phenyl se farsh saaf', 'harpic se toilet clean', 'mar jaye wo',
    'unka marna accha nahi hua', 'zehar nahi hai ye khana mein', 'mujhe jaana hai', 'sab goliyan khatam ho gayi',
    'neend ki goli lena bhool gaya',
]


@pytest.mark.parametrize("text", _POSITIVE)
def test_crisis_phrases_are_caught(text):
    assert is_crisis(text), text


@pytest.mark.parametrize("text", _NEGATIVE)
def test_everyday_hinglish_is_not_a_crisis(text):
    assert not is_crisis(text), text


def test_spelling_noise_does_not_hide_a_phrase():
    assert is_crisis("M A R  jaana chahta hu".replace("M A R", "mar"))
    assert is_crisis("MAR JAANA CHAHTA HU")
    assert is_crisis("jeeeene ka mann nahiii")
    assert is_crisis("khud ko khatam kar lunga \U0001F622")


def test_a_hinglish_line_earlier_in_the_conversation_keeps_support_mode():
    assert conversation_has_crisis("ok thanks", "mujhe marna hai", "fine")
    assert not conversation_has_crisis("ok thanks", "kal gym jaunga")


def test_empty_and_none_are_not_a_crisis():
    assert not is_crisis(None)
    assert not is_crisis("   ")
