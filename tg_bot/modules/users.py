from io import BytesIO
from time import sleep
from typing import Optional, List

from telegram import TelegramError, Chat, Message
from telegram import Update, Bot, ParseMode
from telegram.utils.helpers import mention_html
from telegram.error import BadRequest
from telegram.ext import MessageHandler, Filters, CommandHandler
from telegram.ext.dispatcher import run_async

import tg_bot.modules.sql.users_sql as sql
from tg_bot.modules.helper_funcs.misc import send_to_list
from tg_bot import dispatcher, OWNER_ID, LOGGER, SUDO_USERS
from tg_bot.modules.helper_funcs.filters import CustomFilters

USERS_GROUP = 4


def get_user_id(username):
    # ensure valid userid
    if len(username) <= 5:
        return None

    if username.startswith('@'):
        username = username[1:]

    users = sql.get_userid_by_name(username)

    if not users:
        return None

    elif len(users) == 1:
        return users[0].user_id

    else:
        for user_obj in users:
            try:
                userdat = dispatcher.bot.get_chat(user_obj.user_id)
                if userdat.username == username:
                    return userdat.id

            except BadRequest as excp:
                if excp.message == 'Chat not found':
                    pass
                else:
                    LOGGER.exception("Error extracting user ID")

    return None


@run_async
def broadcast(bot: Bot, update: Update):
    to_send = update.effective_message.text.split(None, 1)
    if len(to_send) >= 2:
        chats = sql.get_all_chats() or []
        failed = 0
        for chat in chats:
            try:
                bot.sendMessage(int(chat.chat_id), to_send[1])
                sleep(0.1)
            except TelegramError:
                failed += 1
                LOGGER.warning("Couldn't send broadcast to %s, group name %s", str(chat.chat_id), str(chat.chat_name))

        update.effective_message.reply_text("Broadcast complete. {} groups failed to receive the message, probably "
                                            "due to being kicked.".format(failed))


@run_async
def restrict_group(bot: Bot, update: Update, args: List[str]) -> str:
    message = update.effective_message

    # Check if there is only one argument
    if len(args) == 1:
        chat_id = args[0]

        # Check if chat_id is valid
        if chat_id.startswith('-'):
            # Check if chat_id is in bot database
            all_chats = sql.get_all_chats() or []
            if any(chat.chat_id == chat_id for chat in all_chats):
                chat_restricted = sql.get_restriction(chat_id)    
                if not chat_restricted:
                    chat_title = bot.get_chat(chat_id).title

                    sudo_users_list = "<b>My Admins:</b>"
                    for user in SUDO_USERS:
                        name = "<a href=\"tg://user?id={}\">{}</a>".format(user, bot.get_chat(user).first_name)
                        sudo_users_list += "\n - {}".format(name)

                    bot.send_message(chat_id = chat_id,
                                     text = "I have been restricted by my admins from this chat. "
                                            "Request any of my admins to add me to this chat.\n\n"
                                            "{admins_list}".format(admins_list = sudo_users_list),
                                     parse_mode = ParseMode.HTML)

                    bot.leave_chat(chat_id)

                    sql.set_restriction(chat_id, restricted = True)

                    message.reply_text("Successfully left chat <b>{}</b>!".format(chat_title),
                                   parse_mode = ParseMode.HTML)
            
                    # Report to sudo users
                    restrictor = update.effective_user  # type: Optional[User]
                    send_to_list(bot, SUDO_USERS,
                                 "{} has restricted me from being added to the chat <b>{}</b>."
                                 .format(mention_html(restrictor.id, restrictor.first_name), chat_title),
                                 html=True)

                else:
                    message.reply_text("I'm already restricted from that chat!")

            else:
                message.reply_text("I can't seem to find the chat in my database. "
                                   "Use /chatlist to obtain a list of chats in my database.")
    
        else:
            message.reply_text("Invalid chat id! Make sure you include the '-' sign in the chat id.")

    else:
        message.reply_text("Incorrect number of arguments. Please use `/restrict chat_id`.",
                           parse_mode = ParseMode.MARKDOWN)

@run_async
def new_member(bot: Bot, update: Update): # Leave group when added to restricted group
    chat = update.effective_chat  # type: Optional[Chat]
    new_members = update.effective_message.new_chat_members
    user = update.effective_user

    if sql.get_restriction(chat.id):
        if not user.id in SUDO_USERS:
            if any(new_mem.id == bot.id for new_mem in new_members):
                update.effective_message.reply_text("I have been restricted by my admins from this chat! "
                                                    "Request any of my admins to add me to this chat.")
                bot.leave_chat(chat.id)

        # Unrestrict group if a sudo user adds bot
        else:
            if any(new_mem.id == bot.id for new_mem in new_members):
                sql.set_restriction(chat.id, restricted = False)

                # Report to sudo users
                send_to_list(bot, SUDO_USERS,
                             "{} has added me to the chat <b>{}</b> and removed my restrictions."
                             .format(mention_html(user.id, user.first_name), chat.title),
                             html=True)

@run_async
def unrestrict_group(bot: Bot, update: Update, args: List[str]) -> str:
    message = update.effective_message
    
    # Check if there is only one argument
    if len(args) == 1:
        chat_id = args[0]

        # Check if chat_id is valid
        if chat_id.startswith('-'):
            # Check if chat_id is in bot database
            all_chats = sql.get_all_chats() or []
            if any(chat.chat_id == chat_id for chat in all_chats):
                chat_restricted = sql.get_restriction(chat_id)
                if chat_restricted:
                    sql.set_restriction(chat_id, restricted = False)
            
                    message.reply_text("Successfully removed all restrictions on the chat with id `{}`"
                                       .format(chat_id), parse_mode = ParseMode.MARKDOWN)
                
                    # Report to sudo users
                    unrestrictor = update.effective_user  # type: Optional[User]
                    send_to_list(bot, SUDO_USERS,
                                 "{} has removed my restrictions on the chat with id <code>{}</code>."
                                 .format(mention_html(unrestrictor.id, unrestrictor.first_name), chat_id),
                                 html=True)
            
                else:
                    message.reply_text("I'm not restricted from that chat!")
        
            else:
                message.reply_text("I can't seem to find the chat in my database. "
                                   "Use /chatlist to obtain a list of chats in my database.")
        
    
        else:
            message.reply_text("Invalid chat id! Make sure you include the '-' sign in the chat id.")

    else:
        message.reply_text("Incorrect number of arguments. Please use `/unrestrict chat_id`.",
                           parse_mode = ParseMode.MARKDOWN)

@run_async
def log_user(bot: Bot, update: Update):
    chat = update.effective_chat  # type: Optional[Chat]
    msg = update.effective_message  # type: Optional[Message]

    sql.update_user(msg.from_user.id,
                    msg.from_user.username,
                    chat.id,
                    chat.title)

    if msg.reply_to_message:
        sql.update_user(msg.reply_to_message.from_user.id,
                        msg.reply_to_message.from_user.username,
                        chat.id,
                        chat.title)

    if msg.forward_from:
        sql.update_user(msg.forward_from.id,
                        msg.forward_from.username)


@run_async
def chats(bot: Bot, update: Update):
    all_chats = sql.get_all_chats() or []
    chatfile = 'List of chats.\n'
    for chat in all_chats:
        chatfile += "{} - ({})\n".format(chat.chat_name, chat.chat_id)

    with BytesIO(str.encode(chatfile)) as output:
        output.name = "chatlist.txt"
        update.effective_message.reply_document(document=output, filename="chatlist.txt",
                                                caption="Here is the list of chats in my database.")


def __user_info__(user_id):
    if user_id == dispatcher.bot.id:
        return """I've seen them in... Wow. Are they stalking me? They're in all the same places I am... oh. It's me."""
    num_chats = sql.get_user_num_chats(user_id)
    return """I've seen them in <code>{}</code> chats in total.""".format(num_chats)


def __stats__():
    return "{} users, across {} chats".format(sql.num_users(), sql.num_chats())


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


__help__ = ""  # no help string

__mod_name__ = "Users"

BROADCAST_HANDLER = CommandHandler("broadcast", broadcast, filters=Filters.user(OWNER_ID))
USER_HANDLER = MessageHandler(Filters.all & Filters.group, log_user)
CHATLIST_HANDLER = CommandHandler("chatlist", chats, filters=CustomFilters.sudo_filter)
RESTRICT_GROUP_HANDLER = CommandHandler("restrict", restrict_group, pass_args=True, 
                                        filters=CustomFilters.sudo_filter)
NEW_MEMBER_HANDLER = MessageHandler(Filters.status_update.new_chat_members, new_member)
UNRESTRICT_GROUP_HANDLER = CommandHandler("unrestrict", unrestrict_group, pass_args=True, 
                                          filters=CustomFilters.sudo_filter)

dispatcher.add_handler(USER_HANDLER, USERS_GROUP)
dispatcher.add_handler(BROADCAST_HANDLER)
dispatcher.add_handler(CHATLIST_HANDLER)
dispatcher.add_handler(RESTRICT_GROUP_HANDLER)
dispatcher.add_handler(NEW_MEMBER_HANDLER)
dispatcher.add_handler(UNRESTRICT_GROUP_HANDLER)
