#!/usr/bin/env python
'''
Usage:
    parse.py <path> <exportpath> <suffix> [<packagename>] [--blacklist=<blacklist>] [--debug] [--cleanup]
    parse.py --jar=<jarfile> <exportpath> [<packagename>] --suffix=<suffix> [--blacklist=<blacklist>] [--debug] [--cleanup]

Options:
    path                        is the path to look java classes into
    exportpath                  is the destination dir to produce classes into
    packagename                 is an optional package name to put in the generated
                                classe files
    -j --jar=<jarfile>          used to look for classes in a jar instead of a path
    -b --blacklist=<blacklist>  indicate a file to filter packages/imports from
    -d --debug                  display more info about what happens
    -c --cleanup                remove old content of exportpath before starting
'''

# TODO
# handling jars

try:
    import plyj.parser as plyj
    import jinja2
    from docopt import docopt
except ImportError:
    print "please install plyj, jinja2 and docopt"
    exit()

import os


parser = plyj.Parser()
env = jinja2.Environment()


def get_type(ptype):
    """Get the string representing a type
    """
    if isinstance(ptype, str):
        return ptype
    elif isinstance(ptype.name, str):
        return ptype.name
    else:
        return ptype.name.value


def render_params(params):
    """A filter to display the parameters of a function call
    """
    return ', '.join(
        '{type} {name}'.format(
            type=get_type(param.type),
            name=param.variable.name)
        for param in params)


def render_params_values(params):
    return ', '.join(
        '{name}'.format(
            name=param.variable.name)
        for param in params)


def import_types(module, blacklist):
    """This gets all the imports done in the original module, not all of
       them are necessary, but it's easier this way
    """
    for i in module.import_declarations:
        if not in_blacklist(i.name.value, blacklist):
            yield 'import %s;\n' % i.name.value
        elif debug:
            print "import %s skipped because it's blacklisted" % i.name.value


env.filters['render_params'] = render_params
env.filters['render_params_values'] = render_params_values
env.filters['get_type'] = get_type


class_template = env.from_string('''\
{% if package %}package {{ package }};{% endif %}
import {{ module.package_declaration.name.value }}.*;
{{ imports }}\

public class {{ cls.name }}{{ suffix }} extends {{ cls.name }} {
    public interface I{{ cls.name }} {\
        {% for method in methods %}
        {{ method.return_type | get_type }} {{ method.name }}({{ method.parameters | render_params }});\
        {% endfor %}
    }

    private I{{ cls.name }} implem = null;

    public void setImplem(I{{ cls.name }} implem) {
        this.implem = implem;
    }

    {% for method in methods %}
    {{ method.return_type | get_type }} {{ method.name }}({{ method.parameters | render_params }}) {
        if (this.implem)
            return this.implem.{{ method.name }}({{ method.parameters | render_params_values }});
    }{% endfor %}
}
''')


def in_blacklist(name, blacklist):
    return any(x in name for x in blacklist)


def get_abstract_classes(path, blacklist):
    """Being given a path, this function will return all the abstract
       classes defined in it
    """
    for path, _, files in os.walk(path):
        for f in files:
            if f.endswith('.java'):
                j = parser.parse_file(file(os.path.join(path, f)))
                if debug:
                    print "parsing %s" % os.path.join(path, f)
                if j:
                    if j.package_declaration:
                        if debug:
                            print "package %s" % j.package_declaration.name.value

                        if in_blacklist(j.package_declaration.name.value, blacklist):
                            if debug:
                                print "skipping package %s because it's blacklisted" % j.package_declaration.name.value
                            continue

                    for tp in j.type_declarations:
                        if (
                            tp and 'public' in tp.modifiers and
                            'abstract' in tp.modifiers
                        ):
                            if debug:
                                print "found abstract class %s in %s" % (tp.name, j.package_declaration)
                            yield j, tp


def get_abstract_methods(tp):
    """Given an abstract class, this will return all its abstract
       methods
    """
    for member in tp.body:
        if (
            isinstance(member, plyj.MethodDeclaration) and
            'abstract' in member.modifiers
        ):
            yield member


if __name__ == '__main__':
    arguments = docopt(__doc__)
    debug = arguments.get('--debug')

    if debug:
        print "passed arguments: %s" % arguments

    outpath = os.path.join(
        arguments['<exportpath>'],
        *arguments.get('<packagename>', '').split('.'))

    if arguments.get('--cleanup'):
        os.rmdir(outpath)

    suffix = arguments.get('<suffix>', '')

    if not os.path.exists(outpath):
        os.makedirs(outpath)

    blacklistfile = arguments.get('--blacklist')
    if blacklistfile:
        with open(blacklistfile) as f:
            blacklist = list(l[:-1] for l in f.readlines())
            print "blacklist: %s" % ';'.join(blacklist)

    else:
        blacklist = []

    for module, cls in get_abstract_classes(arguments['<path>'], blacklist):
        methods = list(get_abstract_methods(cls))
        package = arguments.get('<packagename>')

        javaclass = class_template.render(
            package=package,
            imports=''.join(import_types(module, blacklist)),
            module=module,
            suffix=suffix,
            cls=cls,
            methods=methods)

        with open('%s.java' % (os.path.join(
            outpath, cls.name + suffix)), 'w'
        ) as f:
            f.write(javaclass)