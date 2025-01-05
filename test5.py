# create a car class to store how many people can ride
class car():
    def __init__(self) -> None:
        self.num = 1
# create a electrical car class 
class ecar():
    def __init__(self, car):
        self.car = car
audi = car()
tesla = ecar(audi)
print(audi.num)
print(tesla.car.num)
audi.num += 1
print(audi.num)
print(tesla.car.num)
tesla.car.num += 1
print(audi.num)
print(tesla.car.num)