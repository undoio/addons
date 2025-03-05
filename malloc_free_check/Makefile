memchecker: memchecker.c
	gcc -g -o $@ $<

memchecker.undo: memchecker
	live-record -o $@ ./$<

run: memchecker.undo
	./malloc-free.py $<

all: memchecker.undo

clean:
	rm *.undo *.pyc memchecker
