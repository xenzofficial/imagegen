from flask import Flask, request, render_template_string, send_file, jsonify, Response, send_from_directory
from http.cookies import SimpleCookie
from requests.utils import cookiejar_from_dict
from collections import OrderedDict
import os
import random
import time
import requests
import regex
import base64
import json
app = Flask(__name__)


class ImageFetcher:
    def __init__(
        self,
        cookie_data,
        debug_mode=False,
        timeout_duration=600,
    ):
        self.timeout_duration = timeout_duration
        self.debug_mode = debug_mode

        self.session = self.initialize_session(cookie_data)

        self.setup_error_messages()

    def parse_cookie_data(self, cookie_string):
        cookie = SimpleCookie()
        if os.path.exists(cookie_string):
            with open(cookie_string) as f:
                cookie_string = f.read()

        cookie.load(cookie_string)
        cookies_dict = {}
        cookiejar = None
        for key, morsel in cookie.items():
            cookies_dict[key] = morsel.value
            cookiejar = cookiejar_from_dict(
                cookies_dict, cookiejar=None, overwrite=True
            )
        return cookiejar

    def setup_error_messages(self):
        self.error_messages = {
            "blocked_prompt_error": "Your prompt has been blocked by Bing. Try to change any bad words and try again.",
            "reviewed_prompt_error": "Your prompt is being reviewed by Bing. Try to change any sensitive words and try again.",
            "no_results_error": "Could not get results.",
            "unsupported_lang_error": "This language is currently not supported by Bing.",
            "timeout_error": "Your request has timed out.",
            "redirect_error": "Redirect failed.",
            "bad_images_error": "Bad images.",
            "no_images_error": "No images.",
        }

    def initialize_session(self, cookie_data):
        # Generate random US IP 
        FORWARDED_IP = f"100.{random.randint(43, 63)}.{random.randint(128, 255)}.{random.randint(0, 255)}"
        HEADERS = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "max-age=0",
            "content-type": "application/x-www-form-urlencoded",
            "referrer": "https://www.bing.com/images/create/",
            "origin": "https://www.bing.com",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.63",
            "x-forwarded-for": FORWARDED_IP,
        }

        session = requests.Session()
        session.headers = HEADERS
        session.cookies = self.parse_cookie_data(cookie_data)
        return session

    def handle_error(self, response):
        for error_type, error_msg in self.error_messages.items():
            if error_msg in response.text.lower():
                return Exception(error_type)

    def extract_result_urls(self, response, encoded_prompt):
        if "Location" not in response.headers:
            return None, None
        redirect_url = response.headers["Location"].replace("&nfy=1", "")
        request_id = redirect_url.split("id=")[-1]
        return redirect_url, request_id

    def get_image_urls(self, redirect_url, request_id, encoded_prompt):
        self.session.get(f"https://www.bing.com{redirect_url}")
        polling_url = f"https://www.bing.com/images/create/async/results/{request_id}?q={encoded_prompt}"
        # Poll for results
        start_wait = time.time()
        while True:
            if int(time.time() - start_wait) > self.timeout_duration:
                raise Exception(self.error_messages["timeout_error"])
            response = self.session.get(polling_url)
            if response.status_code != 200:
                raise Exception(self.error_messages["no_results_error"])
            if not response.text or response.text.find("errorMessage") != -1:
                time.sleep(1)
                continue
            else:
                break

        image_links = regex.findall(r'src="([^"]+)"', response.text)
        clean_image_links = [link.split("?w=")[0] for link in image_links]
        clean_image_links = list(set(clean_image_links))

        return clean_image_links

    def submit_request(self, prompt_text, rt_type=4):
        encoded_prompt = requests.utils.quote(prompt_text)
        payload = f"q={encoded_prompt}&qs=ds"
        url = f"https://www.bing.com/images/create?q={encoded_prompt}&rt={rt_type}&FORM=GENCRE"
        response = self.session.post(
            url,
            allow_redirects=False,
            data=payload,
            timeout=self.timeout_duration,
        )
        return response, encoded_prompt

    def execute(self, prompt_text, output_folder):
        # rt=4 means the reward pipeline, run faster than the pipeline without reward (rt=3)
        response, encoded_prompt = self.submit_request(prompt_text, rt_type=4)

        if response.status_code != 302:
            self.handle_error(response)

        print("==> Generating...")
        redirect_url, request_id = self.extract_result_urls(
            response, encoded_prompt
        )
        if redirect_url is None:
            # reward is empty, use rt=3 for slow response
            print(
                "==> Your boosts have run out, using the slow generating pipeline, please wait..."
            )
            response, encoded_prompt = self.submit_request(prompt_text, rt_type=3)
            redirect_url, request_id = self.extract_result_urls(
                response, encoded_prompt
            )
            if redirect_url is None:
                print(
                    "==> Error occurs, please submit an issue at https://github.com/vra/bing_brush, I will fix it as soon as possible."
                )
                return -1

        img_urls = self.get_image_urls(redirect_url, request_id, encoded_prompt)

        print("==> Downloading...")
        os.makedirs(output_folder, exist_ok=True)
        return [url for url in img_urls if not url.endswith(('.svg', '.js'))]



HTML_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Text To Image Generator</title>
    <meta charset="UTF-8"/>
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta property="og:title" content="Text To Image Generator">
    <meta name="description" content="Created image with text">
    <meta property="og:description" content="Created Image With Text">
    <meta property="og:site_name" content="Text To Image">
    <meta property="og:type" content="website">
    <meta property="og:image" content="https://telegra.ph/file/dff2ca1c262f6f21168da.jpg">
    <meta name="copyright" content="al.tech">
    <meta name="robots" content="index, follow">
    <meta name="keywords" content="texttoimg, texttoimage, ai, generateimage, fyp">
    <meta name="theme-color" content="#000000">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css" integrity="sha384-Gn5384xqQ1aoWXA+058RXPxPg6fy4IWvTNh0E263XmFcJlSAwiGgFAW/dAiS6JXm" crossorigin="anonymous">
    <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.min.js" integrity="sha384-JZR6Spejh4U02d8jOt6vLEHfe/JQGiRRSQQxSfFWpi1MquVdAyjUar5+76PVCmYl" crossorigin="anonymous"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.2/css/all.min.css" integrity="sha512-HK5fgLBL+xu6dm/Ii3z4xhlSUyZgTT9tuc/hSrtw6uzJOvgRr2a9jyxxT1ely+B+xFAmJKVSTbpM/CuL7qxO8w==" crossorigin="anonymous">
    <style>
        body {
            font-family: 'Iceland', sans-serif;
            background-color: #0F0F0F;
            color: #00FF9C;
            margin: 0;
            padding: 0;
            overflow: hidden;
            touch-action: none; /* Prevent zoom on touch devices */
            background-repeat: no-repeat;
            background-size: cover;
            background-attachment: fixed;
            height: 100%;
        }
        h1 {
            font-family: 'New Rocker', cursive;
            color: #000;
            font-size: 3em;
            text-transform: uppercase;
            margin: 20px 0;
            text-align: center;
            text-shadow: 0 0 10px #00FF9C;
        }
        form {
            width: 100%;
            max-width: 800px;
            margin: 20px auto;
            padding: 0 20px;
        }
        textarea {
            width: 100%;
            height: 200px;
            padding: 15px;
            font-size: 13px;
            font-family: 'Iceland', sans-serif;
            border: 2px solid #00FF9C;
            border-radius: 8px;
            background-color: #1C1C1C;
            color: #00FF9C;
            box-shadow: 0 0 10px #00FF9C;
            box-sizing: border-box;
            resize: none;
        }
        textarea::placeholder {
            color: #00FF9C;
            font-size: 25px;
            opacity: 0.8;
        }
        button {
            background-color: #00FF9C;
            color: #0F0F0F;
            font-size: 1.4em;
            font-family: 'Iceland', sans-serif;
            border: 2px solid #00FF9C;
            padding: 15px 30px;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 20px;
            width: 100%;
            max-width: 800px;
            text-transform: uppercase;
            transition: all 0.3s ease;
            box-shadow: 0 0 15px #00FF9C;
        }
        button:hover {
            background: linear-gradient(90deg, #00FF9C, #00D57B);
            box-shadow: 0 0 20px #00FF9C;
        }
        button:active {
            transform: scale(0.95);
        }
        .loading {
            border: 8px solid #1C1C1C;
            border-top: 8px solid #00FF9C;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
            display: none;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .image-container {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            justify-content: center;
        }
        .image-container img {
            max-width: 100%;
            max-height: 400px;
            border-radius: 15px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .image-container img:hover {
            transform: scale(1.1);
            box-shadow: 0 8px 16px rgba(0,0,0,0.3);
        }
        section.main2 ul{z-index: -1;display:flex;flex-direction:row;align-items:center;justify-content:center;text-align:center;animation:fadeInUp .8s}section.main2 ul li a{color:#fff;display:flex;text-decoration:none;margin:0 50px;font-size:50px;padding:50px;transition:.2s all}section.main2 ul li a:hover{transition:.2s all;color:#fff}::-webkit-scrollbar,::-webkit-scrollbar{width:0;height:0}@keyframes typewriter{from{width:0}to{width:12.2em}}@keyframes blinkTextCursor{from{border-right-color:rgba(255,255,255,.75)}to{border-right-color:transparent}}@keyframes fadeInUp{from{transform:translate3d(0,150px,0)}to{transform:translate3d(0,0,0);opacity:1}}@keyframes fadeInDown{from{transform:translate3d(0,-1000px,0)}to{transform:translate3d(0,0,0);opacity:1}}
        section.main2 ul li{list-style-type:none}
    </style>
</head>
<body background="https://random-image-pepebigotes.vercel.app/api/random-image">
    <h1>Text To Image</h1>
    <form method="post">
        <textarea type="text" name="prompt" placeholder="Enter your prompt here..." required>{{ request.form['prompt'] if request.form.get('prompt') else '' }}</textarea>
        <button class="raindrop" type="submit">Generate Images</button>
    </form>
    <div class="loading" id="loading"></div>
    <div class="image-container" id="image-container">
        {% for image in images %}
            <img src="{{ image }}" alt="Made With AL-Tech">
        {% endfor %}
    </div><br><br>
    <div class="col-lg-8">
        <headers>
            <section class="main2">
                <ul>
                    <li><a target="_blank" href="https://facebook.com/inu.pembangkang.7"><i class="fab fa-facebook"></i></a></li>
                    <li><a target="_blank" href="https://github.com/xenzofficial"><i class="fab fa-github"></i></a></li>
                    <li><a target="_blank" href="https://instagram.com/al.xo_ox"><i class="fab fa-instagram"></i></a></li>
                </ul>
            </section>
        </headers>
    </div>
    <script>
        window.onload = function() {
            const promptText = sessionStorage.getItem('promptText');
            if (promptText) {
                document.getElementById('prompt').value = promptText;
            }
        }
        function handleSubmit(event) {
            event.preventDefault();
            const loadingElement = document.getElementById('loading');
            const form = event.target;
            const formData = new FormData(form);
            const prompt = formData.get('prompt');
            if (prompt === '') {
                alert('Please enter a prompt.');
                return;
            }
            sessionStorage.setItem('promptText', prompt);
            loadingElement.style.display = 'block';

            // Simulate API call delay
            setTimeout(() => {
                loadingElement.style.display = 'none';
                document.getElementById('image-container').style.display = 'flex';

                // Displaying sample image (replace with actual API response)
                const img = document.createElement('img');
                img.src = 'https://via.placeholder.com/300x300.png?text=404+Not+Found+Error';
                const container = document.getElementById('image-container');
                container.innerHTML = ''; // Clear previous images
                container.appendChild(img);
            }, 3000);
        }
        document.querySelector('form').onsubmit = function() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('image-container').style.display = 'none';
        }
    </script>
</body>
</html>
'''
def cookies():
    try:
        return open("cookies.txt", "r").read()
    except:
        return "MUID=09BAA4DBCDF46C313A35B07BCCF56D28; MUIDB=09BAA4DBCDF46C313A35B07BCCF56D28; MMCASM=ID=1D4056D9BBBB4F48A1ED759375113CF8; SRCHD=AF=NOFORM; SRCHUID=V=2&GUID=076C0EE3C0004C2EBF65F370C6CF143F&dmnchg=1; fdfre=o=1; sbi=cfdlg=1&fredone=1; ANON=A=3468194957DD7A2E84D60A8CFFFFFFFF&E=1e1b&W=1; NAP=V=1.9&E=1dc1&C=35xqMttsWt4AnlP_4cAbz_Tr5X7ceMZ9eb62bV1os-tmnJVeBwTddQ&W=1; PPLState=1; MicrosoftApplicationsTelemetryDeviceId=0a7f0bf4-758a-4b6b-aff0-762b90e89481; _EDGE_S=SID=3D6DA73ED13861713818B23DD0A960FE; _clck=1idom10%7C2%7Cfpf%7C0%7C1683; _clsk=1vmownd%7C1727123006445%7C1%7C0%7Cj.clarity.ms%2Fcollect; KievRPSSecAuth=FAByBBRaTOJILtFsMkpLVWSG6AN6C/svRwNmAAAEgAAACBb8w4sTaXRpMASq6yQMFLb3eYtdzJZ6qKAdpzzsdnGjLEhJuJRIqGkX++AlQwpnJx461oLu+OaQV33Ac13mx0NRV+rHxk+X56W/BzmtrUeS2I9nKQj1+9eaxkxvZ7MfkuLULX/UZk0znwUE1TsONxckSdTid7cIhEo2TyfEKUqMyv3rqMvooBhF9B9fIgPjuKue+jMo6FYApopqdA17F5Hb+HLGrtLyYbfBWHdaX5TM974Ijd2gn5HWVeY5/pE+nwGK0s9w3bF0fGFvePuwqau/Q133g5NPjGF8ASIM9VrVcjO8W4dDur7bCIL7sxWWSZrbACnibV+O8yM0F0KyJcXJj2RW0cSwncK62E+RR+qRtZ6lWcIoedZFYVu9exBylHsh/ty2QfJymrMqM/NOX8ech8it8KswC/bNfWzLwKJcvytc7nIWlghMJycdSAgefwrdnTx4TIVMTKq7xya+zROKHtXQBQ2ex3c1E4StxXeTMGis6v2f5/ltKgRaNERlenCK1cv4LEKzL9IoxjLYa7Lk4GxjX430Ijnh5/gFMTXO/7UAPWXAB3rY0XAyZcMrXBxPJpEHPU3L2tKpm+j60g25y+iYd0xRU1i2E09bAdcSwz3OOyd/CBeZHNZx4SqcO5mZj0q8Vh2BWz6dBpLElGsrmbU3H8Xd9pi8+l5f+9s6HINpYMWz/AlLxjAngBi+5tahMmWgZzGsxjQLYfPekRd4vzZEaWyNZboofjRcld2cu8IHvYnJNXZ2hxnH2oLjZdTSPUuG3PnDbI22ObCZuFyZ77Bg1yVSb8PWvyNrY8GvIFWY0l+DYsKOWfseiBOvnYuGj+aVjxYzVNT9x/kc86rgnHvUUDg93k0xT0mZlZgUSMyVBOddwBx+5YlaFBdmbKMh/9M8p2OlVzQLcSOoEtd6a/40ZJ/CsW28zBeDUKpXH4k4tasxxkFuhQ6FpTIJoskLC/rivtQf6+tdbxupfcC2i95cGFHWc3NZpU9JVBxg9cSOpPJm2nyZx1N5P+kL4q9uCk/PalmdsTBPnLqaJvEiVZ7l7QawiNhqXz7hRXfsqjFZtPALAPFd0/lqsi+edhIPbEmxZo9/qIN94T9BnRdIsnWn3cnbPfrIwQaVIrC8tMefYDnUAla3oXa9e1pm58hOgtPjBzPlL9+xfx0lyOtspRCMSlRnmZfZsHDOG5pyuJ389Ox1LufN8rWEgq0vEzDzLSCd4uXmiPL7ZHzfl4R0myz3GEj2LNIX0tqNYDQEeSKF+fSbP28ta84meMuq1Yk4rNOX9KUTlW3GQxv7Qd4lNQYfWbj/5lN9Auz7rw/G/d25wLla1rMpyheNOq8Dh4//HI1KX4MlBVUOhZFSl2HIxosqk8pJyX7mtsg0Yg6JSD477trMMz+CPizg+0GuDZhoYcx/DZzGVYVRVnHEfLiB/iMXPKCzGf7KFABQr3ejKX8wmnwNMF8Klis7sFu7Ng==; _U=1nsZ8vqNYyqWNl2TfspRCf0Ev71KOLviK5YOSepTTikOddhtQDloVaNMtiYo6ngpbjrWD7oGa3mffbIlfmS3HGDsIf930Wvk4VeNr7JfOKkkJMuuWMYtaoUS3-Qr-8hV1ijPRDCskU2WFiQFqAgK6P5rOvrwvPINl0KPS-P7zISuosSMYip-dbWkabbdl672OGd8QMJRCXITJ7vw9paz4_pz22w3jCBYdM6qrUJvu9Sg; WLS=C=5bacacdba744acad&N=XenzOfficial; SRCHUSR=DOB=20240718&T=1724556414000&TPC=1724524634000&POEX=W; WLID=q/M94c8IhnvzPh7kFRXEFvEDWOhOIAwOizTHO0MDN/W7xIoIGZrLszyZN7CRljSrgz3U5RYtGKklG1Be57UoTWk1YFuYLwQqoq55Y239084=; ak_bmsc=3148C91B89B2A4C8113077FF15B8C1B4~000000000000000000000000000000~YAAQhBfVjN7OJsGRAQAAN/aNIBmKwLCEqQ8yCPIgv1CoPgLhKYJm/Jteze+dXY/oOcHO2Sag3Cdw542EYqWsx05QcxeI22mw8Y1Ug6d6vy6rYOiSy6LWt9YzHIjAQymIiOD6Y9Wbc4feBhcvRyw7zSfSdSYR+kQaX3szYUfxJHdU49npY04RQdxFLlWI9nK4j+Jn54I1GsvtpVaV8JPT7+6Tc2kzPl+nSf9ZvNFxl2OcCKeQTBzk8nuMfF3fUMETXlJ/Vdji21PCpLHvQnt1GbGvvVRIZE0MOsNXowSBUREqG984exSIQeP3XEuOK/PsBplZnFCbjziHBag2MeJVJJMlcO5BsmMsePMoOp79YfTs0Nb8Fn1EOI4opJThLSd8a8PrMIRX; _UR=QS=0&TQS=0&Pn=0; _Rwho=u=m&ts=2024-09-23; _SS=SID=3D6DA73ED13861713818B23DD0A960FE&R=0&RB=0&GB=0&RG=0&RP=0; _RwBf=mta=0&rc=0&rb=0&gb=0&rg=0&pc=0&mtu=0&rbb=0&g=0&cid=&clo=0&v=1&l=2024-09-23T07:00:00.0000000Z&lft=0001-01-01T00:00:00.0000000&aof=0&ard=0001-01-01T00:00:00.0000000&rwdbt=-62135539200&rwflt=-62135539200&o=0&p=MSAAUTOENROLL&c=MR000T&t=1786&s=2024-08-24T18:37:15.3693268+00:00&ts=2024-09-23T20:23:53.7880580+00:00&rwred=0&wls=1&wlb=2&wle=2&ccp=2&cpt=0&lka=0&lkt=0&aad=0&TH=&e=4vZZKSb8QZalyvln0GcGtn6mBYj-b8iWaDl2WAlmh0m5u_n_KvjuwJJs9Pv36VunF_k5KnVzWyS0Rals8z0YeA&A=3468194957DD7A2E84D60A8CFFFFFFFF&rwaul2=0; SRCHHPGUSR=SRCHLANG=id&IG=94A55582523042E28B071FC9AFD2D53D&PV=9.0.0&DM=1&CW=424&CH=829&SCW=424&SCH=829&BRW=MW&BRH=MT&DPR=1.7&UTC=420&HV=1727123031&WTS=63862719803&PRVCW=424&PRVCH=829&HBOPEN=2; bm_sv=FCD63D195F1628DAFB80E5FDA029B4D5~YAAQZbjbF4eTLg2SAQAA6kuOIBmxmg/+0U/QCCflwVmixSqLvf1onybjjDdj30qslkgo0P/C7z9aduSQT8A0ilTOsc1vneFaD2+gombFK+JkssW4kMU0HpyEYO7PfKaUDVv6FE6IltMty7WxHmPDr0VsI0kdGZRFN3HJgXH3rKKPkFQUyfqmF6sAs/gWO1K6kkwRJNMGToqJN8xmDKp7MKOe/K8uES4sma3mZDY7zx2IACQOCmHiSVkBljhhlw==~1; _HPVN=CS=eyJQbiI6eyJDbiI6NCwiU3QiOjAsIlFzIjowLCJQcm9kIjoiUCJ9LCJTYyI6eyJDbiI6NCwiU3QiOjAsIlFzIjowLCJQcm9kIjoiSCJ9LCJReiI6eyJDbiI6NCwiU3QiOjAsIlFzIjowLCJQcm9kIjoiVCJ9LCJBcCI6dHJ1ZSwiTXV0ZSI6dHJ1ZSwiTGFkIjoiMjAyNC0wOS0yM1QwMDowMDowMFoiLCJJb3RkIjowLCJHd2IiOjAsIlRucyI6MCwiRGZ0IjpudWxsLCJNdnMiOjAsIkZsdCI6MCwiSW1wIjoxMywiVG9ibiI6MH0="

def saveImage(img_urls):
    result = []
    for image_url in img_urls:
        response = requests.get(image_url)
        if response.status_code == 200:
            file_name = image_url.split("/")[-1]
            save_path = os.path.join("result/images", file_name) + ".jpg"
            with open(save_path, "wb") as file:
                file.write(response.content)
            print(f"Save image to: {save_path}")
            clean_url = request.host_url.rstrip('/') + "/" + save_path.replace("\\", "/")
            result.append(clean_url)
            continue
        else:
            continue
    return result

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        prompt = request.form['prompt']
        fetcher = ImageFetcher(cookie_data=cookies(), debug_mode=False, timeout_duration=600)
        img_urls = fetcher.execute(prompt_text=prompt, output_folder="result/images")
        try:
            path = saveImage(img_urls)
            return render_template_string(HTML_TEMPLATE, images=path)
        except:
            return render_template_string(HTML_TEMPLATE, images=["https://media.tenor.com/IHdlTRsmcS4AAAAM/404.gif"])
    return render_template_string(HTML_TEMPLATE, images=["https://th.bing.com/th/id/OIG1.LkdpsS76gawWdWo8hQLQ?w=173&h=173&c=6&r=0&o=5&dpr=1.7&pid=ImgGn"])

@app.route('/api', methods=['GET'])
def api():
    prompt = request.args.get('prompt')
    if not prompt:
        return jsonify({"error": "Parameter 'prompt' tidak ditemukan."}), 400
    fetcher = ImageFetcher(cookie_data=cookies(), debug_mode=False, timeout_duration=600)
    img_urls = fetcher.execute(prompt_text=prompt, output_folder="result/images")
    result = saveImage(img_urls)
    response_data = OrderedDict([
        ("success", True),
        ("creator", "Mas AL"),
        ("prompt", prompt),
        ("result", result)
    ])
    response_json = json.dumps(response_data, separators=(',', ':'), indent=2)
    return Response(response=response_json, mimetype='application/json'), 200



@app.route('/result/images/<path:filename>')
def download_file(filename):
    return send_from_directory('result/images', filename)


if __name__ == "__main__":
    app.run(debug=True)

