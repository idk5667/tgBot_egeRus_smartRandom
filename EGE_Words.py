# -*- coding: utf-8 -*-
import os
import re
import json
import random
import threading
import telebot
from telebot import types
from time import sleep
from telebot.apihelper import ApiTelegramException
import shutil

# --- КОНСТАНТЫ И НАСТРОЙКИ ---
TOKEN = 'че то, секрет че, теперь знаю, что нельзя на гит выкладывать токен'
ADMIN_ID = 0.23498723947283979843298423897432987324798432989483278942749234923749
bot = telebot.TeleBot(TOKEN)
USER_DATA = "user_data.json"

# Создаем "замок" для файла, чтобы потоки не мешали друг другу
file_lock = threading.Lock()

MAX_USER_WORDS = 15
NUMBER_OF_TASKS = [4, 5, 7, 9, 10, 11, 12, 13, 14, 15]

# Группировка по типам интерфейса
TYPE_INSERT_LETTERS = [9, 10, 11, 12, 15]
TYPE_SEPERATE_TOGETGHER = [13, 14]
TYPE_STRESS = [4]
TYPE_PARONYMS = [5]
TYPE_MORPHOLOGY = [7]


# --- РАБОТА С JSON (БАЗА ДАННЫХ) ---

def get_base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def load_json():
    path = os.path.join(get_base_dir(), USER_DATA)
    with file_lock:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка загрузки JSON: {e}")
                return {}
    return {}


def save_json(data):
    path = os.path.join(get_base_dir(), USER_DATA)
    bak_path = path + ".bak"

    with file_lock:
        try:
            if os.path.exists(path):
                shutil.copy(path, bak_path)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"Критическая ошибка сохранения JSON: {e}")


def ensure_user_structure(data, uid, task_num):
    uid, task_num = str(uid), str(task_num)
    changed = False

    if task_num not in data:
        data[task_num] = {"main_words": {}}
        changed = True

    if uid not in data[task_num]:
        data[task_num][uid] = {
            "words": {},
            "weights": [],
            "step_up": 0.6,
            "step_down": 0.2
        }
        changed = True

    if changed:
        save_json(data)
    return data


def get_task_data(task_num, user_id):
    data = load_json()
    uid, t_num = str(user_id), str(task_num)

    data = ensure_user_structure(data, uid, t_num)

    main_w = data[t_num].get("main_words", {})
    user_w = data[t_num][uid].get("words", {})

    all_answers = list(main_w.keys()) + list(user_w.keys())

    if "weights" not in data[t_num][uid]:
        data[t_num][uid]["weights"] = []

    weights = data[t_num][uid]["weights"]

    if len(weights) < len(all_answers):
        diff = len(all_answers) - len(weights)
        weights.extend([1.0] * diff)
        data[t_num][uid]["weights"] = weights
        save_json(data)

    elif len(weights) > len(all_answers):
        weights = weights[:len(all_answers)]
        data[t_num][uid]["weights"] = weights
        save_json(data)

    return {
        "answers": all_answers,
        "wrongs": [v[0] for v in main_w.values()] + [v[0] for v in user_w.values()],
        "tasks": [v[1] for v in main_w.values()] + [v[1] for v in user_w.values()],
        "expls": [v[2] for v in main_w.values()] + [v[2] for v in user_w.values()],
        "weights": weights
    }


def delete_user_message(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass


def send_or_edit_interface(chat_id, message_id, mode, text, markup):
    try:
        if mode == 0:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        else:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="HTML")
    except ApiTelegramException as e:
        if "message is not modified" not in str(e):
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")


def get_admin_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for x in NUMBER_OF_TASKS:
        buttons.append(types.InlineKeyboardButton(f"➕ Общак {x}", callback_data=f"admin_task_{x}"))
        buttons.append(types.InlineKeyboardButton(f"🗑 Удал. {x}", callback_data=f"admin_del_list_{x}"))
    kb.add(*buttons)
    kb.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu"))
    return kb


# --- ГЕНЕРАЦИЯ ЗАДАНИЯ ---

def create_choice_markup(task_num, idx, text_correct, text_wrong):
    markup = types.InlineKeyboardMarkup()
    b_right = types.InlineKeyboardButton(text_correct, callback_data=f"ans_r_{task_num}_{idx}")
    b_wrong = types.InlineKeyboardButton(text_wrong, callback_data=f"ans_w_{task_num}_{idx}")
    btns = [b_right, b_wrong]
    random.shuffle(btns)

    if len(text_correct) > 9 or len(text_wrong) > 9:
        markup.add(btns[0])
        markup.add(btns[1])
    else:
        markup.row(btns[0], btns[1])

    markup.add(types.InlineKeyboardButton("⬅️ В меню", callback_data=f"task_{task_num}"))
    return markup


def send_task_or_edit(chat_id, message_id, mode, task_num):
    task_data = get_task_data(task_num, chat_id)
    if not task_data["answers"]:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➕ Добавить слово", callback_data=f"add_{task_num}"))
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"task_{task_num}"))
        send_or_edit_interface(chat_id, message_id, mode, "📂 Список пуст! Добавьте слова.", kb)
        return

    idx = random.choices(range(len(task_data["answers"])), weights=task_data["weights"], k=1)[0]
    t_int = int(task_num)

    if t_int in TYPE_INSERT_LETTERS:
        text = f"<b>Задание №{task_num}</b>\n\nВыбери верное написание:\n\n👉 <code>{task_data['tasks'][idx].upper()}</code>"
        markup = create_choice_markup(task_num, idx, task_data['answers'][idx], task_data['wrongs'][idx])
    elif t_int in TYPE_STRESS:
        text = f"<b>Задание №{task_num}</b>\n\nГде верно ударение?\n\n👉 <b>{task_data['tasks'][idx].lower()}</b>"
        markup = create_choice_markup(task_num, idx, task_data['answers'][idx], task_data['wrongs'][idx])
    elif t_int in TYPE_SEPERATE_TOGETGHER:
        # Для 13 и 14 заданий
        text = f"<b>Задание №{task_num}</b>\n\nВыберите правильное написание слова:\n\n👉 <code>{task_data['tasks'][idx].upper()}</code>"
        markup = create_choice_markup(task_num, idx, task_data['answers'][idx], task_data['wrongs'][idx])
    elif t_int in TYPE_PARONYMS:
        text = f"<b>Задание №{task_num}</b>\n\nВыберите значение для слова:\n💎 <b>{task_data['answers'][idx].upper()}</b>"
        markup = create_choice_markup(task_num, idx, task_data['tasks'][idx], task_data['wrongs'][idx])
    elif t_int in TYPE_MORPHOLOGY:
        text = f"<b>Задание №{task_num}</b>\n\nВерная форма слова:\n\n<code>{task_data['tasks'][idx].upper()}</code>"
        markup = create_choice_markup(task_num, idx, task_data['answers'][idx], task_data['wrongs'][idx])
    else:
        text = f"<b>Задание №{task_num}</b>\n\n{task_data['tasks'][idx]}"
        markup = create_choice_markup(task_num, idx, task_data['answers'][idx], task_data['wrongs'][idx])

    send_or_edit_interface(chat_id, message_id, mode, text, markup)


# --- ЛОГИКА ДОБАВЛЕНИЯ СЛОВ (КОНВЕЙЕР) ---


def start_adding_word(message, task_num, old_mid, is_admin=False):
    uid = str(message.chat.id)
    data = load_json()

    if not is_admin:
        ensure_user_structure(data, uid, task_num)
        user_words = data[str(task_num)][uid].get("words", {})
        if len(user_words) >= MAX_USER_WORDS:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"task_{task_num}"))
            bot.edit_message_text("🚫 Лимит слов превышен!", uid, old_mid, reply_markup=kb)
            return

    prefix = "🌟 ОБЩАК" if is_admin else "👤 ЛИЧНОЕ"
    prompt = "Введите <b>ПРАВИЛЬНЫЙ</b> ответ:"

    if str(task_num) == "5":
        prompt = "Введите <b>Значение</b>:"
    elif str(task_num) == "4":
        prompt = "Введите ответ (ударение Большой буквой):"
    elif int(task_num) in TYPE_SEPERATE_TOGETGHER:
        prompt = "Напиши как выглядит задание (через слэш), пример: <code>По/этому пути мы шли</code>"

    text = f"<b>{prefix} | Задание {task_num}</b>\n\nШаг 1/3: {prompt}"

    try:
        bot.edit_message_text(text, message.chat.id, old_mid, parse_mode="HTML")
        last_id = old_mid
    except:
        try:
            bot.delete_message(message.chat.id, old_mid)
        except:
            pass
        sent = bot.send_message(message.chat.id, text, parse_mode="HTML")
        last_id = sent.message_id

    bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: step_2_wrong(m, task_num, last_id, is_admin))


def step_2_wrong(message, task_num, last_bot_mid, is_admin):
    if not message.text or message.text.startswith('/'): return
    delete_user_message(message)
    user_input = message.text.strip()

    if int(task_num) in TYPE_SEPERATE_TOGETGHER:
        next_txt = f"✅ Условие: <b>{user_input}</b>\n\nШаг 2: Напишите <b>слитно</b> или <b>раздельно</b>:"
        bot.edit_message_text(next_txt, message.chat.id, last_bot_mid, parse_mode="HTML")
        bot.register_next_step_handler_by_chat_id(message.chat.id,
                                                  lambda m: step_3_task(m, task_num, user_input, last_bot_mid,
                                                                        is_admin))
        return

    correct = user_input
    next_txt = f"✅ Ответ: <b>{correct}</b>\n\nШаг 2: Введите вариант с <b>ОШИБКОЙ</b>:"

    if int(task_num) in TYPE_INSERT_LETTERS:
        next_txt = f"✅ Ответ: <b>{correct}</b>\n\nШаг 2: Введите вариант с <b>ОШИБКОЙ</b> (отличие по сравнению с правильным ответом должно быть в 1 букву):"
    elif str(task_num) == "5":
        next_txt = f"✅ Значение: <b>{correct}</b>\n\nШаг 2: Введите <b>Пароним, который подходит под описание</b> значение:"

    bot.edit_message_text(next_txt, message.chat.id, last_bot_mid, parse_mode="HTML")
    bot.register_next_step_handler_by_chat_id(message.chat.id,
                                              lambda m: step_3_task(m, task_num, correct, last_bot_mid, is_admin))


def step_3_task(message, task_num, correct, last_bot_mid, is_admin):
    if not message.text: return
    delete_user_message(message)
    user_input = message.text.strip()
    t_str, uid = str(task_num), str(message.chat.id)

    # 13-14 Задания
    if int(task_num) in TYPE_SEPERATE_TOGETGHER:
        task_phrase = correct
        parts = [p for p in task_phrase.split() if "/" in p]
        if not parts: return
        w_parts = parts[0].split("/")
        if "слитн" in user_input.lower():
            final_c, final_w = w_parts[0] + w_parts[1], w_parts[0] + " " + w_parts[1]
        else:
            final_c, final_w = w_parts[0] + " " + w_parts[1], w_parts[0] + w_parts[1]

        data = load_json()
        ensure_user_structure(data, uid, t_str)
        target = data[t_str]["main_words"] if is_admin else data[t_str][uid]["words"]
        target[final_c] = [final_w, task_phrase, ""]
        save_json(data)
        show_ask_explanation(message.chat.id, task_num, final_c, last_bot_mid, is_admin)
        return


# Паронимы
    if str(task_num) == "5":
        bot.edit_message_text(f"✅ Пароним принят.\n\nШаг 3: Введите <b>неправильный пароним к этому значению</b> значение:",
                              message.chat.id, last_bot_mid, parse_mode="HTML")
        bot.register_next_step_handler_by_chat_id(message.chat.id,
                                                  lambda m: step_finish_paronym(m, task_num, user_input, last_bot_mid,
                                                                                is_admin, correct))
        return

        # ... (выше код для 13-14 и паронимов с их return-ами)

        # Орфография и Ударения
    # ВАЖНО: изначально ставим None, чтобы проверить, выделили ли мы слово
    final_c = None
    final_w = None
    task_p = ""
    if int(task_num) in TYPE_INSERT_LETTERS:
        listR = correct.split()
        listW = user_input.split()
        # Если это предложение (несколько слов)
        if len(listR) == len(listW) and len(listR) > 1:
            for i in range(len(listR)):
                if listR[i].strip().lower() != listW[i].strip().lower():
                    final_c = listR[i].strip()
                    final_w = listW[i].strip()
                    # Генерируем маску (слово с точкой)
                    diff_idxs = [j for j in range(min(len(final_c), len(final_w))) if
                                 final_c[j].lower() != final_w[j].lower()]
                    word_as_list = list(final_w)
                    if diff_idxs:
                        word_as_list[diff_idxs[0]] = "."
                    else:
                        word_as_list.append(".")
                    # Создаем фразу для задания, заменяя только ошибочное слово на маску
                    task_p = user_input.replace(listW[i], "".join(word_as_list))
                    break
        # Если слово одно или если цикл выше не нашел отличий (на всякий случай)
        if final_c is None:
            final_c = correct.strip()
            final_w = user_input.strip()
            diff_idxs = [j for j in range(min(len(final_c), len(final_w))) if
                         final_c[j].lower() != final_w[j].lower()]
            word_as_list = list(final_w)
            if diff_idxs:
                word_as_list[diff_idxs[0]] = "."
            else:
                word_as_list.append(".")
            task_p = "".join(word_as_list)
    elif int(task_num) in TYPE_STRESS:
        final_c = correct.strip()
        final_w = user_input.strip()
        task_p = final_c.lower()
    # ФИНАЛЬНОЕ СОХРАНЕНИЕ (выровняй строго под if int(task_num) in TYPE_INSERT_LETTERS)
    data = load_json()
    ensure_user_structure(data, uid, t_str)
    target = data[t_str]["main_words"] if is_admin else data[t_str][uid]["words"]
    # Теперь в final_c точно будет только слово
    target[final_c] = [final_w, task_p, ""]
    save_json(data)
    show_ask_explanation(message.chat.id, task_num, final_c, last_bot_mid, is_admin)
def step_finish_paronym(message, task_num, correct, last_bot_mid, is_admin, val_desc=""):
    delete_user_message(message)
    data = load_json()
    uid = str(message.chat.id)
    ensure_user_structure(data, uid, task_num)
    target = data[str(task_num)]["main_words"] if is_admin else data[str(task_num)][uid]["words"]
    target[correct] = [message.text.strip(), val_desc, ""]
    save_json(data)
    show_ask_explanation(message.chat.id, task_num, correct, last_bot_mid, is_admin)


def show_ask_explanation(chat_id, task_num, correct, mid, is_admin):
    adm_flag = "1" if is_admin else "0"
    kb = types.InlineKeyboardMarkup()
    safe_correct = correct.replace(" ", "_SPACE_")
    kb.add(
        types.InlineKeyboardButton("Да, добавить", callback_data=f"ask_ex_y_{task_num}_{adm_flag}_{safe_correct}"),
        types.InlineKeyboardButton("Нет, сохранить", callback_data=f"ask_ex_n_{task_num}_{adm_flag}_{safe_correct}")
    )
    bot.edit_message_text(f"✅ Слово <b>{correct}</b> готово. Добавить объяснение?", chat_id, mid, reply_markup=kb,
                          parse_mode="HTML")


def finish_logic(chat_id, task_num, correct, mid, is_admin, expl=""):
    data = load_json()
    t_str, uid = str(task_num), str(chat_id)
    target = data[t_str]["main_words"] if is_admin else data[t_str][uid]["words"]
    real_correct = correct.replace("_SPACE_", " ")

    if real_correct in target:
        target[real_correct][2] = expl
    elif correct in target:
        target[correct][2] = expl

    if not is_admin:
        ensure_user_structure(data, uid, task_num)  # Безопасность
        main_count = len(data[t_str].get("main_words", {}))
        user_count = len(data[t_str][uid].get("words", {}))
        total_words = main_count + user_count
        weights = data[t_str][uid].get("weights", [])
        while len(weights) < total_words:
            weights.append(1.0)
        data[t_str][uid]["weights"] = weights

    save_json(data)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back" if is_admin else f"task_{t_str}"))
    bot.edit_message_text(f"✅ Слово <b>{real_correct}</b> сохранено и добавлено в тест!", chat_id, mid, reply_markup=kb,
                          parse_mode="HTML")

def apply_new_steps(message, t_num, old_mid):
    if message.text and message.text.startswith('/'):
        return
    delete_user_message(message)
    nums = re.findall(r"\d+\.?\d*", message.text)
    if len(nums) < 2:
        try:
            bot.edit_message_text(
                "⚠️ <b>Ошибка ввода!</b>\n\nНужно ввести два числа через пробел.\nПример: <code>1.2 0.4</code>",
                message.chat.id, old_mid,
                parse_mode="HTML"
            )
        except:
            pass
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: apply_new_steps(m, t_num, old_mid))
        return
    try:
        up, down = float(nums[0]), float(nums[1])
        data = load_json()
        uid = str(message.chat.id)
        t_str = str(t_num)
        ensure_user_structure(data, uid, t_str)
        data[t_str][uid]["step_up"] = round(up, 2)
        data[t_str][uid]["step_down"] = round(down, 2)
        current_weights_count = len(data[t_str][uid].get("weights", []))
        data[t_str][uid]["weights"] = [1.0] * current_weights_count
        save_json(data)
        kb_back = types.InlineKeyboardMarkup()
        kb_back.add(types.InlineKeyboardButton("⬅️ Назад к заданию", callback_data=f"task_{t_num}"))
        bot.edit_message_text(
            f"✅ <b>Настройки изменены!</b>\n\n"
            f"📈 Штраф (ошибка): +{up}\n"
            f"📉 Бонус (успех): -{down}\n\n"
            f"♻️ Все веса задания {t_num} сброшены в 1.0",
            message.chat.id, old_mid,
            reply_markup=kb_back,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Ошибка в apply_new_steps: {e}")
        bot.edit_message_text("❌ Произошла системная ошибка. Попробуйте снова.",
                              message.chat.id, old_mid)


def change_weight_logic(message, t_num, old_mid, txt):
    if message.text and message.text.startswith('/'): return
    delete_user_message(message)
    nums = re.findall(r"\d+\.?\d*", message.text)
    if len(nums) != 2:
        bot.edit_message_text(f"{txt}\n\n" + "⚠️⚠️⚠️⚠️⚠️⚠️⚠️",
                              message.chat.id, old_mid, parse_mode="HTML")
        bot.register_next_step_handler_by_chat_id(message.chat.id,
                                                  lambda m: change_weight_logic(m, t_num, old_mid, txt))
    else:
        data = load_json()
        idx, val = int(nums[0]) - 1, float(nums[1])
        uid = str(message.chat.id)
        try:
            data[str(t_num)][uid]["weights"][idx] = round(val, 1)
            save_json(data)
            kb_back = types.InlineKeyboardMarkup()
            kb_back.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"task_{t_num}"))
            bot.edit_message_text(f"✅ Вес слова №{idx + 1} успешно изменен на {val}",
                                  message.chat.id, old_mid, reply_markup=kb_back)
        except:
            bot.edit_message_text("❌ Ошибка! Неверный номер слова в списке." + f"{txt}\n\n" + "⚠️⚠️⚠️⚠️⚠️⚠️⚠️",
                                  message.chat.id, old_mid)
            bot.register_next_step_handler_by_chat_id(message.chat.id,
                                                      lambda m: change_weight_logic(m, t_num, old_mid, txt))


# --- ОБРАБОТЧИК КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    uid, mid = call.message.chat.id, call.message.message_id

    if call.data.startswith("ask_ex_"):
        parts = call.data.split("_")
        # Обработка ситуаций, когда в слове были пробелы (ask_ex_y_13_0_по_SPACE_этому)
        choice = parts[2]
        t_num = parts[3]
        is_adm = (parts[4] == "1")

        # Собираем остаток обратно в строку и возвращаем пробелы
        raw_word = "_".join(parts[5:])
        correct = raw_word.replace("_SPACE_", " ")

        if choice == "n":
            finish_logic(uid, t_num, correct, mid, is_adm, expl="")
        else:
            prompt_txt = f"📝 Введите объяснение для <b>{correct}</b>:"
            p_msg = bot.edit_message_text(prompt_txt, uid, mid, parse_mode="HTML")
            bot.register_next_step_handler(p_msg, lambda m: [
                delete_user_message(m),
                finish_logic(uid, t_num, correct, mid, is_adm, m.text.strip())
            ])

    elif call.data == "main_menu":
        kb = types.InlineKeyboardMarkup()
        btns = [types.InlineKeyboardButton(f"{x} задание", callback_data=f"task_{x}") for x in NUMBER_OF_TASKS]
        kb.row(*btns[:3])
        kb.row(*btns[3:6])
        kb.row(*btns[6:])
        btn = types.InlineKeyboardButton("Инструкция (очень советую прочитать)", callback_data="/help")
        kb.row(btn)
        try:
            bot.edit_message_text("<b>Главное меню:</b>", uid, mid, reply_markup=kb, parse_mode="HTML")
        except:
            bot.send_message(uid, "<b>Главное меню:</b>", reply_markup=kb, parse_mode="HTML")

    elif call.data == "/help":
        help_text = (
            "<b>📖 Справка по тренажеру</b>\n\n"
            "Этот бот помогает запоминать сложные слова для ЕГЭ через систему весов (в определенном смысле как упрощенное ai).\n\n"
            "• <b>Как это работает:</b> чем чаще вы ошибаетесь, тем чаще слово выпадает в тесте.\n"
            "• <b>Личное и Общак:</b> вы можете добавлять свои слова, которые будут видны только вам.\n"
            "• <b>Настройка сложности:</b> можно менять 'штраф' за ошибку в настройках задания, и антиштраф за верно решенное.\n\n"
            "<i>Прошу вас только не жмакать постоянно старт, особенно во время добавления слов и т.д, когда ввести короче что то надо</i>"
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ Назад в меню", callback_data="main_menu"))
        bot.edit_message_text(chat_id=uid, message_id=mid, text=help_text, reply_markup=kb, parse_mode="HTML")

    elif call.data.startswith("task_"):
        t_num = call.data.split("_")[-1]
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton('🚀 Решать', callback_data=f'solve_{t_num}'))
        kb.row(types.InlineKeyboardButton('➕ Добавить слово', callback_data=f'add_{t_num}'),
               types.InlineKeyboardButton('🗑 Удалить слово', callback_data=f'del_list_{t_num}'))
        kb.row(types.InlineKeyboardButton('⚙️ Сложность', callback_data=f'w_settings_{t_num}'),
               types.InlineKeyboardButton('📊 Веса', callback_data=f'w_edit_{t_num}'))
        kb.add(types.InlineKeyboardButton('⬅️ Меню', callback_data='main_menu'))
        bot.edit_message_text(f"📝 <b>Задание №{t_num}</b>", uid, mid, reply_markup=kb, parse_mode="HTML")

    elif call.data == "admin_back":
        bot.edit_message_text("🛠 <b>УПРАВЛЕНИЕ ОБЩЕЙ БАЗОЙ</b>", uid, mid, reply_markup=get_admin_keyboard(),
                              parse_mode="HTML")


    elif call.data.startswith("admin_task_"):
        start_adding_word(call.message, call.data.split("_")[-1], mid, is_admin=True)

    elif call.data.startswith("add_"):
        start_adding_word(call.message, call.data.split("_")[-1], mid, is_admin=False)

    elif call.data.startswith("del_list_"):
        t_num = call.data.split("_")[-1]
        data = load_json()
        u_dict = data.get(str(t_num), {}).get(str(uid), {}).get("words", {})
        if not u_dict:
            bot.answer_callback_query(call.id, "Список пуст!")
            return
        kb = types.InlineKeyboardMarkup()
        for w in u_dict:
            kb.add(types.InlineKeyboardButton(f"🗑 {w}", callback_data=f"confirm_user_del_{t_num}_{w}"))
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"task_{t_num}"))
        bot.edit_message_text(f"🗑 <b>Личное удаление (Задание {t_num})</b>", uid, mid, reply_markup=kb,
                              parse_mode="HTML")

    elif call.data.startswith("admin_del_list_"):
        t_num = call.data.split("_")[-1]
        data = load_json()
        m_dict = data.get(str(t_num), {}).get("main_words", {})
        if not m_dict:
            bot.answer_callback_query(call.id, "Общак пуст!")
            return
        kb = types.InlineKeyboardMarkup()
        for w in m_dict:
            kb.add(types.InlineKeyboardButton(f"🗑 {w}", callback_data=f"adm_confirm_del_{t_num}_{w}"))
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
        bot.edit_message_text(f"🗑 <b>Общак удаление (Задание {t_num})</b>", uid, mid, reply_markup=kb,
                              parse_mode="HTML")

    elif call.data.startswith("confirm_user_del_"):
        parts = call.data.split("_")
        t_num, word = parts[3], parts[4]
        data = load_json()
        t_s, uid_s = str(t_num), str(uid)

        if word in data[t_s][uid_s]["words"]:
            main_count = len(data[t_s].get("main_words", {}))
            user_keys = list(data[t_s][uid_s]["words"].keys())

            if word in user_keys:
                local_index = user_keys.index(word)
                absolute_index = main_count + local_index
                del data[t_s][uid_s]["words"][word]

                weights = data[t_s][uid_s]["weights"]
                if absolute_index < len(weights):
                    weights.pop(absolute_index)
                    data[t_s][uid_s]["weights"] = weights

                save_json(data)
                bot.answer_callback_query(call.id, "✅ Удалено")
        call.data = f"del_list_{t_num}"
        handle_query(call)

    elif call.data.startswith("adm_confirm_del_"):
        parts = call.data.split("_")
        t_num, word = parts[3], parts[4]
        data = load_json()
        t_s = str(t_num)

        if word in data[t_s]["main_words"]:
            main_keys = list(data[t_s]["main_words"].keys())
            if word in main_keys:
                idx = main_keys.index(word)
                del data[t_s]["main_words"][word]

                for user_key in data[t_s]:
                    if user_key != "main_words":
                        u_weights = data[t_s][user_key].get("weights", [])
                        if idx < len(u_weights):
                            u_weights.pop(idx)

                save_json(data)
                bot.answer_callback_query(call.id, "✅ Удалено из общака и у всех юзеров")

        call.data = f"admin_del_list_{t_num}"
        handle_query(call)

    elif call.data.startswith("solve_"):
        send_task_or_edit(uid, mid, 1, call.data.split("_")[-1])


    elif call.data.startswith("ans_"):

        # Разбираем данные от кнопки: ans_r_13_5 (тип_результат_номер_индекс)

        parts = call.data.split("_")

        res = parts[1]

        t_num = int(parts[2])

        idx = int(parts[3])

        # Загружаем данные

        info = get_task_data(t_num, uid)

        data = load_json()

        u_data = data[str(t_num)][str(uid)]

        weights = u_data["weights"]

        # --- НАЧАЛО ВАЖНОГО БЛОКА IF/ELSE ---

        # Внимательно следи за вертикальной чертой отступа!

        if res == 'r':

            # === ЕСЛИ ОТВЕТ ВЕРНЫЙ ===

            # 1. Уменьшаем вес (чтобы слово выпадало реже)

            new_w = weights[idx] - u_data.get("step_down", 0.2)

            weights[idx] = round(max(0.2, new_w), 1)

            # 2. Формируем текст успеха

            # Для 5 задания (паронимы) показываем пару

            if t_num == 5:

                txt = f"✅ <b>Верно!</b>\n\n{info['tasks'][idx].upper()}\n\n{info['expls'][idx]}"

            elif t_num == 4:
                txt = f"✅ <b>Верно!</b>\n\n{info['answers'][idx]}\n\n{info['expls'][idx]}"


            else:

                # Для остальных (включая 13 и 14) показываем правильный ответ

                txt = f"✅ <b>Верно!</b>\n\n{info['answers'][idx].upper()}\n\n{info['expls'][idx]}"


        else:

            # === ЕСЛИ ОТВЕТ НЕВЕРНЫЙ (ELSE строго под IF) ===

            # 1. Увеличиваем вес (чтобы слово выпадало чаще)

            new_w = weights[idx] + u_data.get("step_up", 1.0)

            weights[idx] = round(new_w, 1)

            # 2. Формируем текст ошибки

            if t_num == 5:

                txt = f"❌ <b>Ошибка!</b>\n\nВерно: {info['tasks'][idx].upper()}\n\n{info['expls'][idx]}"

            elif t_num == 4:

                txt = f"❌ <b>Ошибка!</b>\n\nВерно: {info['answers'][idx]}\n\n{info['expls'][idx]}"

            else:

                txt = f"❌ <b>Ошибка!</b>\n\nВерно: {info['answers'][idx].upper()}\n\n{info['expls'][idx]}"

        # --- КОНЕЦ БЛОКА IF/ELSE ---

        # Сохраняем веса и отправляем результат

        data[str(t_num)][str(uid)]["weights"] = weights

        save_json(data)

        bot.edit_message_text(txt, uid, mid, parse_mode="HTML")

        # Пауза, чтобы юзер успел прочитать, прав он или нет

        sleep(2.25)

        # Сразу выдаем следующее задание

        send_task_or_edit(uid, mid, 1, t_num)

    elif call.data.startswith("w_settings_"):
        t_num = call.data.split("_")[-1]
        data = load_json()
        u_conf = data[str(t_num)][str(uid)]
        txt = (f"🛠 <b>Настройка сложности (Задание {t_num})</b>\n"
               f"Текущий шаг вверх: +{u_conf.get('step_up', 1.0)}\n"
               f"Текущий шаг вниз: -{u_conf.get('step_down', 0.2)}\n\n"
               f"Введите два числа через пробел (например: <code>1.5 0.3</code>).\n"
               f"⚠️ После смены шага веса сбросятся!")
        prompt = bot.edit_message_text(txt, uid, mid, parse_mode="HTML")
        bot.register_next_step_handler(prompt, lambda m: apply_new_steps(m, t_num, mid))

    elif call.data.startswith("admin_del_list_"):
        t_num = call.data.split("_")[-1]
        data = load_json()
        m_dict = data.get(str(t_num), {}).get("main_words", {})
        if not m_dict:
            bot.answer_callback_query(call.id, "Общак пуст!")
            return
        kb = types.InlineKeyboardMarkup()
        for i, w in enumerate(m_dict.keys()):
            btn_text = f"🗑 {w[:30]}..." if len(w) > 30 else f"🗑 {w}"
            kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_confirm_del_{t_num}_{i}"))
        kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back"))
        bot.edit_message_text(f"🗑 <b>Общак удаление (Задание {t_num})</b>", uid, mid, reply_markup=kb, parse_mode="HTML")


    elif call.data.startswith("w_edit_"):
        t_num = call.data.split("_")[-1]
        info = get_task_data(t_num, uid)
        txt = "<b>Список слов и весов:</b>\n"
        for i, w in enumerate(info["answers"]):
            txt += f"{i + 1}. {w} — {info['weights'][i]}\n"
        txt += "\n⚠️ Введите <b>Номер</b> слова и <b>Вес</b> через пробел (напр: 1 0.5):"
        prompt = bot.edit_message_text(txt, uid, mid, parse_mode="HTML")
        bot.register_next_step_handler(prompt, lambda m: change_weight_logic(m, t_num, mid, txt))

    try:
        bot.answer_callback_query(call.id)
    except:
        pass


@bot.message_handler(commands=['start'])
def start_cmd(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    kb = types.InlineKeyboardMarkup()
    btns = [types.InlineKeyboardButton(f"{x} задание", callback_data=f"task_{x}") for x in NUMBER_OF_TASKS]
    kb.row(*btns[:3])
    kb.row(*btns[3:6])
    kb.row(*btns[6:])
    btn = types.InlineKeyboardButton(text="Инструкция (очень советую прочитать)", callback_data="/help")
    kb.row(btn)
    bot.send_message(message.chat.id, "<b>Главное меню тренажера ЕГЭ:</b>", reply_markup=kb, parse_mode="HTML")


@bot.message_handler(commands=['admin_add'])
def admin_add_start(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    bot.send_message(message.chat.id, "🛠 <b>УПРАВЛЕНИЕ ОБЩЕЙ БАЗОЙ</b>", reply_markup=get_admin_keyboard(),
                     parse_mode="HTML")


if __name__ == '__main__':
    bot.set_my_commands([
        telebot.types.BotCommand("/start", "Главное меню")
    ])

    print("Бот запущен. Включена защита от падения сети...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"Сетевой сбой: {e}")
            print("Переподключение через 5 секунд...")
            sleep(5)