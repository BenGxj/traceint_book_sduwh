import json
import time
import traceback

import ddddocr
import requests
import websocket

from utils.utils import (log, save_recognized_image, save_unrecognized_image,
                         take_seat_name, wait_time)
from utils.request import post, verify_cookie, need_captcha


# status=false时可以预定
def seat_prereserve(cookie):
    if not verify_cookie(cookie):
        log('cookie无效，请重新输入cookie')
        return

    ocr = ddddocr.DdddOcr()

    with open('json/reserve/reserve_para.json', 'r') as f:
        prereserve_para = json.load(f)
    with open('json/reserve/reserve_headers.json', 'r') as f:
        prereserve_headers = json.load(f)
    prereserve_headers['Cookie'] = cookie
    prereserve_para["variables"]["key"] = '31,74'

    with open('json/reserve/pre_10_headers.json', 'r') as f:
        pre_headers = json.load(f)
    with open('json/reserve/pre_10_para.json', 'r') as f:
        pre_para = json.load(f)
    pre_headers['Cookie'] = cookie

    with open('json/reserve/verify_captcha_headers.json', 'r') as f:
        verify_captcha_headers = json.load(f)
    with open('json/reserve/verify_captcha_para.json', 'r') as f:
        verify_captcha_para = json.load(f)
    verify_captcha_headers['Cookie'] = cookie

    with open('json/reserve/captcha_headers.json', 'r') as f:
        captcha_headers = json.load(f)
    with open('json/reserve/captcha_para.json', 'r') as f:
        captcha_para = json.load(f)
    captcha_headers['Cookie'] = cookie

    with open('json/reserve/get_end_time_headers.json', 'r') as f:
        get_end_time_headers = json.load(f)
    with open('json/reserve/get_end_time_para.json', 'r') as f:
        get_end_time_para = json.load(f)
    get_end_time_headers['Cookie'] = cookie

    log('开始等待验证cookie时间')
    wait_time(12, 29)
    if not verify_cookie(cookie):
        log('cookie无效，请重新输入cookie')
        return
    else:
        log('cookie有效，请等待预定时间')

    log('开始等待预定时间')
    wait_time(12, 30)
    try:
        resp_get_end_time = post(get_end_time_para,
                                 get_end_time_headers).json()
        if need_captcha():

            log('尝试识别验证码')
            resp_captcha = post(captcha_para, captcha_headers).json()
            captcha_code = resp_captcha['data']['userAuth']['prereserve'][
                'captcha']['code']
            captcha_website = resp_captcha['data']['userAuth']['prereserve'][
                'captcha']['data']
            image_byte = requests.get(captcha_website).content

            captcha = ocr.classification(image_byte)
            log(f'识别验证码为{captcha}')

            verify_captcha_para['variables']['captcha'] = captcha
            verify_captcha_para['variables']['captchaCode'] = captcha_code
            resp_verify_captcha = post(verify_captcha_para,
                                       verify_captcha_headers).json()

            while not resp_verify_captcha['data']['userAuth']['prereserve'][
                    'verifyCaptcha']:

                log(f'{captcha_code}尝试失败，保存验证码图片后开始下一次尝试')
                save_unrecognized_image(
                    image_byte, '_'.join(
                        (captcha_code, captcha_website.split('/')[-1])))

                resp_captcha = post(captcha_para, captcha_headers).json()
                captcha_code = resp_captcha['data']['userAuth']['prereserve'][
                    'captcha']['code']
                captcha_website = resp_captcha['data']['userAuth'][
                    'prereserve']['captcha']['data']

                image_byte = requests.get(captcha_website).content
                captcha = ocr.classification(image_byte)

                log(f'识别验证码为{captcha}')
                verify_captcha_para['variables']['captcha'] = captcha
                verify_captcha_para['variables']['captchaCode'] = captcha_code
                resp_verify_captcha = post(verify_captcha_para,
                                           verify_captcha_headers).json()

            log(f'验证码尝试成功，验证码为{captcha}')
            log(json.dumps(resp_verify_captcha, indent=4, ensure_ascii=False))
        else:
            log('已验证验证码')
    except Exception:
        log('错误')
        traceback.print_exc()

    # TODO:修改为若排队未完成且排队人数为-1且超出时间则一直连接wss连接
    try:
        try:
            wss_url = resp_verify_captcha['data']['userAuth']['prereserve'][
                'setStep1']
        except Exception:
            wss_url = resp_get_end_time['data']['userAuth']['prereserve'][
                'queeUrl']
        log(f'wss连接地址{wss_url}')
        wss = websocket.create_connection(wss_url, timeout=30)
        log('create_connection连接成功')
    except Exception:
        log('create_connection连接异常')
        traceback.print_exc()

    # TODO 此处改为更通用的写法
    resp_queue = requests.get(
        'https://wechat.v2.traceint.com/quee/success?sid=21001936&schId=126&t=13b1b5fbc10742ac0fd0a0ff510ea917'
    )
    queue_num = int(resp_queue.content)
    log(f'前方排队{queue_num}人')

    while queue_num > 0:
        log(f'前方排队{queue_num}人')
        if queue_num > 100:
            time.sleep(2)
        # TODO 此处改为更通用的写法
        resp_queue = requests.get(
            'https://wechat.v2.traceint.com/quee/success?sid=21001936&schId=126&t=13b1b5fbc10742ac0fd0a0ff510ea917'
        )
        queue_num = int(resp_queue.content)
    log(f'前方排队{queue_num}人')
    log('排队完成')
    try:
        log(f'getStep:{get_step(cookie)}')
    except Exception:
        log('getStep失败')

    resp = post(pre_para, pre_headers).json()
    while 'errors' in resp:
        log('请求座位失败')
        log(json.dumps(resp, indent=4, ensure_ascii=False))

    seats = resp["data"]["userAuth"]["prereserve"]["libLayout"]["seats"]
    seats.sort(key=take_seat_name)
    for seat in seats:
        if seat['name'] == "" or seat['name'] is None:
            log("该座位不存在")
            continue
        if not seat["status"]:
            prereserve_para["variables"]["key"] = seat["key"]
            log(f"开始预定{seat['name']}号")
            prereserve_resp = post(prereserve_para, prereserve_headers).json()
            try:
                if prereserve_resp["data"]["userAuth"]["prereserve"]["save"]:
                    log(f"预定成功，座位为{seat['name']}号")
                    break
                else:
                    log(f"预定{seat['name']}号失败")
                    log(
                        json.dumps(prereserve_resp,
                                   indent=4,
                                   ensure_ascii=False))
            except Exception:
                log(f"预定{seat['name']}号失败")
                log(json.dumps(prereserve_resp, indent=4, ensure_ascii=False))
                continue
        else:
            log(f"{seat['name']}号座位已有人")

    # 查看排队数据，已增强系统精准性
    resp_queue = requests.get(
        'https://wechat.v2.traceint.com/quee/success?sid=21001936&schId=126&t=13b1b5fbc10742ac0fd0a0ff510ea917'
    )
    queue_num = int(resp_queue.content)
    log(f'抢座完成后排队人数{queue_num}')

    try:
        log(f'getStep:{get_step(cookie)}')
    except Exception:
        log('getStep失败')

    if 'wss' in dir():  # vars() locals().keys()均可
        wss.close()
        log('create_connection连接关闭')

    resp_queue = requests.get(
        'https://wechat.v2.traceint.com/quee/success?sid=21001936&schId=126&t=13b1b5fbc10742ac0fd0a0ff510ea917'
    )
    queue_num = int(resp_queue.content)
    log(f'关闭websocket后排队人数{queue_num}')

    if 'image_byte' in dir():
        log('开始写入验证码图片')
        save_recognized_image(
            image_byte, '_'.join(
                (captcha, captcha_code, captcha_website.split('/')[-1])))


if __name__ == '__main__':
    seat_prereserve('')
