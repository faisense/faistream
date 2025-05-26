from faivision.observer import Observer


class CLIObserver(Observer):
    def update(self, value):
        print("Value changed: ", value)