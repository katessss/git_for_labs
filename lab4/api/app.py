from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from confluent_kafka import Producer
import os

app = FastAPI()

class Order(BaseModel):
    id: int
    item: str 

KAFKA_HOST = os.environ.get('KAFKA_HOST')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC')
producer = Producer({'bootstrap.servers': KAFKA_HOST})


def delivery_report(err, msg):
    if err is not None:
        print(f"FAILED: Message delivery failed: {err}")
    else:
        print(f"SUCCESS: Delivered to {msg.topic()} [{msg.partition()}]")


@app.post("/order")
def create_order(order: Order):
    message_value = order.item.encode('utf-8')
    try:
        producer.produce(
            KAFKA_TOPIC, 
            key=str(order.id).encode('utf-8'),
            value=message_value,
            callback=delivery_report
        )
        
        producer.poll(0)
        
        return {"status": "ok", "message": f"Заказ '{order.item}' отправлен в Kafka Topic '{KAFKA_TOPIC}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка брокера Kafka: {str(e)}")

@app.get("/")
def health_check():
    if producer.flush(timeout=1) == 0:
        return {"status": "API is running, Kafka Producer OK"}
    else:
        raise HTTPException(status_code=500, detail="Kafka Producer is DOWN")