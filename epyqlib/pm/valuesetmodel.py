import pathlib

import attr
import graham
import marshmallow

import epyqlib.attrsmodel
import epyqlib.pm.parametermodel
import epyqlib.treenode


class SaveCancelled(Exception):
    pass


def create_blank(parameter_model=None):
    value_set = ValueSet(parameter_model=parameter_model)
    _post_load(value_set)

    return value_set


def loads(s, path=None):
    root = graham.schema(Root).loads(s).data
    value_set = ValueSet(path=path)

    if path is not None:
        value_set.path = pathlib.Path(path).absolute()

    _post_load(value_set, root=root)

    return value_set


def load(f):
    value_set = loads(f.read(), path=f.name)

    return value_set


def loadp(path):
    with open(path) as f:
        return load(f)


def _post_load(value_set, root=None):
    if root is None:
        root = Root()

    if value_set.model is None:
        value_set.model = epyqlib.attrsmodel.Model(
            root=root,
            columns=columns,
        )


def copy_parameter_data(
        value_set,
        human_names=True,
        base_node=None,
        calculate_unspecified_min_max=False,
        symbol_root=None,
):
    def traverse(node, _):
        if isinstance(node, epyqlib.pm.parametermodel.Parameter):
            if human_names:
                name = node.name
            else:
                name = ':'.join((
                    node.original_multiplexer_name,
                    node.original_signal_name,
                ))

            minimum = node.minimum
            maximum = node.maximum

            if calculate_unspecified_min_max:
                query_multiplexed_message, = symbol_root.nodes_by_attribute(
                    attribute_value='Parameter Query',
                    attribute_name='name',
                )
                signal, = query_multiplexed_message.nodes_by_attribute(
                    attribute_value=node.uuid,
                    attribute_name='parameter_uuid',
                )

                minimum, maximum = signal.calculated_min_max()

            value_set.model.root.append_child(
                Parameter(
                    name=name,
                    parameter_uuid=node.uuid,
                    factory_default=node.default,
                    minimum=minimum,
                    maximum=maximum,
                ),
            )

            value_set.model.root.children.sort()

    if base_node is None:
        base_node = value_set.parameter_model.root

    base_node.traverse(
        call_this=traverse,
        internal_nodes=False,
    )


def name_attrib():
    attrib = attr.ib(
        convert=str,
    )
    graham.attrib(
        attribute=attrib,
        field=marshmallow.fields.String(),
    )

    return attrib


def decimal_attrib(**kwargs):
    attrib = attr.ib(
        convert=epyqlib.attrsmodel.to_decimal_or_none,
        **kwargs,
    )
    graham.attrib(
        attribute=attrib,
        field=marshmallow.fields.Decimal(
            allow_none=kwargs.get('default', False) is None,
            as_string=True,
        ),
    )
    
    return attrib


@graham.schemify(tag='parameter')
@epyqlib.attrsmodel.ify()
@epyqlib.utils.qt.pyqtify()
@attr.s(hash=False)
class Parameter(epyqlib.treenode.TreeNode):
    name = name_attrib()
    value = decimal_attrib(default=None)
    user_default = decimal_attrib(default=None)
    factory_default = decimal_attrib(default=None)
    minimum = decimal_attrib(default=None)
    maximum = decimal_attrib(default=None)

    parameter_uuid = epyqlib.attrsmodel.attr_uuid(
        default=None,
        allow_none=True,
    )

    epyqlib.attrsmodel.attrib(
        attribute=parameter_uuid,
        human_name='Parameter UUID',
    )

    uuid = epyqlib.attrsmodel.attr_uuid()

    def __attrs_post_init__(self):
        super().__init__()

    def can_drop_on(self, node):
        return False

    can_delete = epyqlib.attrsmodel.childless_can_delete


Root = epyqlib.attrsmodel.Root(
    default_name='Value Set',
    valid_types=(Parameter,),
)

types = epyqlib.attrsmodel.Types(
    types=(
        Root,
        Parameter,
    ),
)


@attr.s
class ValueSet:
    parameter_model = attr.ib(default=None)
    model = attr.ib(default=None)
    path = attr.ib(default=None)
    filters = attr.ib(
        default=(
            ('Parameter Value Set', ['pmvs']),
            ('All Files', ['*']),
        )
    )

    def save(self, parent=None):
        if self.path is None:
            path = epyqlib.utils.qt.file_dialog(
                filters=self.filters,
                parent=parent,
                save=True,
                caption='Save Value Set As',
            )

            if path is None:
                raise SaveCancelled()

            self.path = pathlib.Path(path)

        sorted_children = sorted(self.model.root.children)

        # TODO: remove this backwards compat and just use recent
        #       attrs everywhere
        evolve = getattr(attr, 'evolve', attr.assoc)

        sorted_root = evolve(
            self.model.root,
            children=sorted_children
        )

        s = graham.dumps(sorted_root, indent=4).data

        with open(self.path, 'w') as f:
            f.write(s)

            if not s.endswith('\n'):
                f.write('\n')


# TODO: CAMPid 943896754217967154269254167
def merge(name, *types):
    return tuple((x, name) for x in types)


columns = epyqlib.attrsmodel.columns(
    merge('name', *types.types.values()),
    merge('value', Parameter),
    merge('user_default', Parameter),
    merge('factory_default', Parameter),
    merge('minimum', Parameter),
    merge('maximum', Parameter),
    merge('parameter_uuid', Parameter),
    merge('uuid', *types.types.values()),
)