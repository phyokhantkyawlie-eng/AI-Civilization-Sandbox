"""Authored, seeded portrait-dialogue lines. No acceptance/transfer decisions here."""
STYLES = {
 'mira': {
  'greeting': ('Oh, hello. It is lovely to have a little company.', 'Come sit a moment. How can I help?', 'Hello. It is good to take a gentle pause together.'),
  'smalltalk': ('The village feels peaceful when everyone has a little time for each other.', 'I like watching the berry bushes recover. Little things need patience.'),
  'shared': ('Here, this berry is yours. I hope it helps.', 'There you are. Please take good care of yourself.'),
  'refusal': ('I am sorry. I need to keep my supplies this time.', 'I wish I could, but I cannot spare a berry right now.'),
  'thank_help': ('You are very welcome. I am glad it helped.', 'A little kindness can go a long way.')},
 'nyra': {
  'greeting': ('Hello. A quiet conversation would be welcome.', 'You have my attention. What is on your mind?', 'Hello. Shall we compare a few observations?'),
  'smalltalk': ('It pays to notice the small changes around us.', 'I prefer to understand a situation before rushing into it.'),
  'shared': ('One berry. Use it carefully.', 'I can spare this one. I hope it is useful.'),
  'refusal': ('I would rather keep a reserve for now.', 'I cannot safely spare any of my supplies.'),
  'thank_help': ('I remember. I am pleased it was useful.', 'You are welcome. It was a reasonable thing to do.')},
 'kairo': {
  'greeting': ('Hey! Good to see you. What is happening?', 'A familiar face! Got a moment to chat?', 'Hey there! I am glad our paths crossed.'),
  'smalltalk': ('There is always another corner of the village to explore!', 'A good adventure is better when you have someone to tell about it.'),
  'shared': ('Here you go! One berry for the road.', 'Happy to help. This one is yours!'),
  'refusal': ('Sorry! I need to hang on to my supplies this time.', 'I cannot spare one right now. I still need a meal myself.'),
  'thank_help': ('Of course! Glad I could help.', 'That is what neighbors are for!')},
 'ren': {
  'greeting': ('Well, hello. What brings you over?', 'A short break? All right. You have my attention.', 'Hello again. I can spare a little time for conversation.'),
  'smalltalk': ('A little planning saves a great deal of trouble later.', 'Supplies do not manage themselves. Still, conversation costs very little.'),
  'shared': ('There. One berry. Remember who helped you.', 'I can spare this one. Make it count.'),
  'refusal': ('I would rather keep what I have. Supplies are not endless.', 'Not this time. I am keeping a reserve.'),
  'thank_help': ('Good. I do appreciate someone who remembers a favor.', 'You are welcome. Sensible neighbors are worth helping.')},
}
COMMON = {
 'question': ('Could you spare one berry?', 'May I ask for a berry?'),
 'offer': ('Would you like one of my berries?', 'I have a berry to offer, if you have room.'),
 'consider': ('Let me consider that for a moment.', 'Let me see what I can spare.'),
 'thanks': ('Thank you. That helps.', 'I appreciate the berry. Thank you.'),
 'acknowledge': ('I understand. I will find another way.', 'All right. Thank you for answering.'),
 'reply': ('It is good to have some company.', 'Hello. What would you like to talk about?'),
}


def line(social,speaker,partner,topic):
    from .characters import CHARACTERS
    key=CHARACTERS[speaker.id][1]
    if topic=='npc_check':
        if partner.hunger>=55:return 'You look hungry. How are you holding up?'
        if partner.energy<=30:return 'You look tired. Are you getting enough rest?'
        return 'I thought I would check in. How are you doing?'
    if topic=='npc_thanks':
        return social.dialogue_rng.choice(('I wanted to thank you for the berry you shared.', 'Your help earlier meant a lot. Thank you for sharing your food.'))
    if topic=='npc_casual':topic='smalltalk'
    if topic=='reply_warm':
        intent=social.session_for(speaker).intent
        if intent and intent.kind.value=='THANK_PLAYER':return 'You are welcome. I am glad I could help.'
        if speaker.hunger>=55:return 'Thank you for asking. I could use a meal, but I am managing.'
        if speaker.energy<=30:return 'Thanks for checking. I could use a little rest.'
        return 'It is good to talk with you. I am doing all right.'
    if topic=='reply_brief':return 'Thanks for stopping by. Take care.'
    if topic=='decline_offer':return 'No, thank you. Please keep it.'
    if topic=='offer_declined':return 'Of course. No worries.'
    if topic=='prepare_offer':return 'One moment; let me get it.'
    if topic=='npc_goodbye':return social.dialogue_rng.choice(('Thank you for the conversation. Take care.', 'It was good to speak with you. See you around.'))
    if topic=='offer' and speaker.food==0:return 'I am sorry. I no longer have a berry to offer.'
    if topic in ('how','need_food'):
        if speaker.hunger>=85: status='I really need something to eat.'
        elif speaker.hunger>=55: status='I am getting hungry. A meal would help.'
        elif speaker.energy<=20: status='I am exhausted. I need a proper rest.'
        elif speaker.energy<=40: status='I am a little tired, but I can manage.'
        else: status='I am doing all right. My needs are taken care of for now.'
        if speaker.food==0:status+=' I have no berries in my bag.'
        elif speaker.personality.get('resource_focus',.5)>.8:status+=' I am keeping an eye on my supplies.'
        if speaker.personality.get('risk_aversion',.5)>.8:status+=' I prefer to be prepared.'
        goal=getattr(speaker.goal,'purpose',None)
        intent={'food':'I was planning to gather food.','chicken meal':'I had a cooked meal in mind.',
                'cook':'I was planning to cook.','rest':'I was planning a little rest.',
                'explore':'I was exploring the village.'}.get(goal)
        if intent:status+=' '+intent
        elif speaker.current_action=='REST':status+=' I was taking a short rest.'
        return social.dialogue_rng.choice((status,'Thank you for asking. '+status))
    if topic=='greeting':
        trust=social.trust_for(speaker,partner.id)
        if trust<=-20:return 'I can spare a moment. Let us keep things civil.'
        if trust>=20:return social.dialogue_rng.choice(('It is good to see someone I trust.',STYLES[key]['greeting'][0]))
    if topic=='refusal' and speaker.food==0:
        return 'I do not have any berries to share right now.'
    options=STYLES[key].get(topic,COMMON.get(topic,STYLES[key]['greeting']))
    available=[text for text in options
               if social.tick-social.repeated_lines.get((speaker.id,partner.id,text),-100000)>=social.settings.repeat_ticks]
    return social.dialogue_rng.choice(available or options)
