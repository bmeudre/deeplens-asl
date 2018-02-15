import os
import greengrasssdk
import awscam
import mo
import cv2
from threading import Thread

client = greengrasssdk.client('iot-data')
iot_topic = '$aws/things/{}/infer'.format(os.environ['AWS_IOT_THING_NAME'])
client.publish(topic=iot_topic, payload="Starting...")

jpeg = None
Write_To_FIFO = True

class FIFO_Thread(Thread):
    def __init__(self):
        ''' Constructor. '''
        Thread.__init__(self)

    def run(self):
        fifo_path = "/tmp/results.mjpeg"
        if not os.path.exists(fifo_path):
            os.mkfifo(fifo_path)
        f = open(fifo_path,'w')
        client.publish(topic=iot_topic, payload="Opened Pipe")
        while Write_To_FIFO:
            try:
                f.write(jpeg.tobytes())
            except IOError as e:
                continue

def greengrass_infinite_infer_run():
    try:
        # Optimizing model (you have to update MxNet with: pip3 install mxnet --upgrade)
        input_width = 224
        input_height = 224
        model_name = "deeplens-asl"
        error, model_path = mo.optimize(model_name, input_width, input_height)
        if error:
            raise Exception(error)

        # Loading model
        model = awscam.Model(model_path, {"GPU": 1})
        client.publish(topic=iot_topic, payload="Model loaded")

        # Model variables
        model_type = "classification"
        labels = ['a','b','c','d','e','f','g','h','i','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','spok','like','f**k']
        topk = 1

        # Streaming results
        results_thread = FIFO_Thread()
        results_thread.start()
        client.publish(topic=iot_topic, payload="Inference is starting")

        # Preparing sentence display
        actual_letter = ''
        actual_frame_count = 0
        message = ''
        minimum_count = 20
        space_count = 30
        reset_count = 70
        total_frame_count = 0

        # Inference loop
        while True:

            # Retrieving last frame
            total_frame_count = total_frame_count + 1
            ret, frame = awscam.getLastFrame()
            if ret == False:
                raise Exception("Failed to get frame from the stream")

            # Resizing frame
            height, width, channels = frame.shape
            frame_cropped = frame[0:height, (width-height)/2:width-(width-height)/2]
            frame_resize = cv2.resize(frame_cropped, (input_width, input_height))
            infer_output = model.doInference(frame_resize)
            parsed_results = model.parseResult(model_type, infer_output)
            top_k = parsed_results[model_type][0:topk]

            output_frame = frame_cropped

            # Filtering 40% confidence
            if (top_k[0]["prob"] > 0.4):
                # Writing inference results
                letter = labels[top_k[0]["label"]]
                if (actual_letter == letter):
                    actual_frame_count = actual_frame_count + 1
                    if (actual_frame_count == minimum_count):
                        message = message + letter
                else:
                    actual_frame_count = 1
                    actual_letter = labels[top_k[0]["label"]]
            	cv2.putText(output_frame, '{}: {:.2f}'.format(labels[top_k[0]["label"]], top_k[0]["prob"]), (0,20), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 165, 20), 4)
            
                # Publishing results to IoT topic
                #msg = "{"
    	        #prob_num = 0
            	#for obj in top_k:
                #    if prob_num == topk-1:
                #    	msg += '"{}": {:.2f}'.format(labels[obj["label"]], obj["prob"])
                #    else:
                #    	msg += '"{}": {:.2f},'.format(labels[obj["label"]], obj["prob"])
                #    prob_num += 1
            	#msg += "}"
            	#client.publish(topic=iot_topic, payload=msg)
            else:
                # Handling whitespaces
                if (actual_letter != ''):
                    actual_frame_count = 0
                    actual_letter = ''
                else :
                    actual_frame_count = actual_frame_count + 1
                    if (actual_frame_count == space_count and not message.endswith(" ")):
                        message = message + " "
                    if (actual_frame_count == reset_count):
                        message = ""

            # Handling caret
            total_message = message
            if (total_frame_count % 4 < 2) :
                total_message = message + "_"

            # Writing sentence
            cv2.putText(output_frame, total_message, (0,height-50), cv2.FONT_HERSHEY_SIMPLEX, 4, (45, 145, 236), 4)
            
            # Streaming frame
            global jpeg
            ret, jpeg = cv2.imencode('.jpg', output_frame)

    except Exception as e:
        msg = "Lambda failed: " + str(e)
        client.publish(topic=iot_topic, payload=msg)

    # Asynchronously schedule this function to be run again in 15 seconds
    Timer(15, greengrass_infinite_infer_run).start()

# Execute the function above
greengrass_infinite_infer_run()

# This is a dummy handler and will not be invoked
# Instead the code above will be executed in an infinite loop for our example
def function_handler(event, context):
    return
